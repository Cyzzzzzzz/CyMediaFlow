from __future__ import annotations

import asyncio
from pathlib import Path

from app.application.nfo_service import NfoPreviewService
from app.application.ports import (
    BindingRepositoryPort,
    EpisodeArtworkGeneratorPort,
    MediaCatalogPort,
    MediaProbePort,
)
from app.core.errors import MediaNotFoundError
from app.domain.artwork import (
    IMAGE_EXTENSIONS,
    ArtworkExtractionIssue,
    SeasonArtworkExtractionResult,
)
from app.domain.episode_mapping import resolve_local_season


class SeasonArtworkExtractionService:
    """Refreshes episode sidecar artwork for one local season."""

    def __init__(
        self,
        catalog: MediaCatalogPort,
        bindings: BindingRepositoryPort,
        preview_service: NfoPreviewService,
        media_probe: MediaProbePort,
        artwork_generator: EpisodeArtworkGeneratorPort,
        concurrency: int = 2,
    ) -> None:
        self._catalog = catalog
        self._bindings = bindings
        self._preview_service = preview_service
        self._media_probe = media_probe
        self._artwork_generator = artwork_generator
        self._concurrency = max(1, concurrency)

    async def extract(self, media_id: str, season_number: int) -> SeasonArtworkExtractionResult:
        item = self._catalog.get_media(media_id)
        if item is None:
            raise MediaNotFoundError(media_id)
        binding = self._bindings.get(media_id)
        configured_season = binding.season_number if binding else 1
        excluded_folders = self._excluded_folders(binding.metadata if binding else {})
        preview = self._preview_service.preview(
            media_id,
            season_number=configured_season,
            overwrite_existing=True,
        )

        target_entries = [
            entry
            for entry in preview.entries
            if entry.category == "regular"
            and resolve_local_season(
                Path(entry.video_relative_path), entry.parsed.season, configured_season
            )
            == season_number
        ]
        skipped: list[ArtworkExtractionIssue] = []
        candidates: list[tuple[Path, Path, str]] = []
        for entry in target_entries:
            relative_path = Path(entry.video_relative_path)
            relative_text = relative_path.as_posix()
            if self._folder_is_excluded(entry.folder, excluded_folders):
                skipped.append(ArtworkExtractionIssue(relative_text, "FOLDER_EXCLUDED"))
                continue
            video_path = item.root_path / relative_path
            output_path = self._existing_episode_sidecar(video_path) or video_path.with_name(
                f"{video_path.stem}-thumb.jpg"
            )
            candidates.append((video_path, output_path, relative_text))

        semaphore = asyncio.Semaphore(self._concurrency)

        async def generate_one(
            video_path: Path, output_path: Path, relative_text: str
        ) -> tuple[str, str, str]:
            async with semaphore:
                probe = await self._media_probe.probe(video_path)
                duration = probe.media.duration_seconds if probe.media else None
                result = await self._artwork_generator.generate(
                    video_path, output_path, duration, overwrite_existing=True
                )
            if result.created:
                return "created", output_path.relative_to(item.root_path).as_posix(), ""
            return "failed", relative_text, result.warning_code or "ARTWORK_NOT_CREATED"

        outcomes = await asyncio.gather(
            *(generate_one(video, output, relative) for video, output, relative in candidates)
        )
        created_files: list[str] = []
        failed: list[ArtworkExtractionIssue] = []
        for status, relative_path, reason in outcomes:
            if status == "created":
                created_files.append(relative_path)
            else:
                failed.append(ArtworkExtractionIssue(relative_path, reason))

        return SeasonArtworkExtractionResult(
            media_id=media_id,
            season_number=season_number,
            target_count=len(target_entries),
            created_files=tuple(sorted(created_files)),
            skipped_files=tuple(sorted(skipped, key=lambda issue: issue.relative_path)),
            failed_files=tuple(sorted(failed, key=lambda issue: issue.relative_path)),
        )

    @staticmethod
    def _excluded_folders(metadata: dict[str, object]) -> set[str]:
        value = metadata.get("nfo_excluded_folders")
        if not isinstance(value, list):
            return set()
        return {
            SeasonArtworkExtractionService._normalize_folder(folder)
            for folder in value
            if isinstance(folder, str)
        }

    @staticmethod
    def _normalize_folder(value: str) -> str:
        normalized = Path(value.replace("\\", "/")).as_posix().strip("/").casefold()
        return normalized or "."

    @classmethod
    def _folder_is_excluded(cls, folder: str, excluded_folders: set[str]) -> bool:
        normalized = cls._normalize_folder(folder)
        return any(
            excluded == "."
            or normalized == excluded
            or normalized.startswith(f"{excluded}/")
            for excluded in excluded_folders
        )

    @staticmethod
    def _existing_episode_sidecar(video_path: Path) -> Path | None:
        return next(
            (
                video_path.with_name(f"{video_path.stem}{suffix}{extension}")
                for suffix in ("-thumb", ".thumb", "-poster", "")
                for extension in IMAGE_EXTENSIONS
                if video_path.with_name(
                    f"{video_path.stem}{suffix}{extension}"
                ).is_file()
            ),
            None,
        )
