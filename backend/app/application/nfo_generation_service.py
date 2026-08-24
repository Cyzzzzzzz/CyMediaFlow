from __future__ import annotations

import asyncio
import os
from collections.abc import Mapping
from contextlib import suppress
from dataclasses import dataclass, replace
from pathlib import Path
from uuid import uuid4
from xml.etree import ElementTree as ET

from app.application.nfo_document_builder import NfoDocumentBuilder
from app.application.nfo_merge_service import NfoDocumentMerger
from app.application.nfo_service import NfoPreviewService
from app.application.ports import (
    BindingRepositoryPort,
    EpisodeArtworkGeneratorPort,
    IgnoreMarkerPort,
    MediaCatalogPort,
    MediaProbePort,
    MetadataProviderPort,
    RemoteArtworkDownloaderPort,
)
from app.core.errors import MediaNotFoundError, NfoGenerationError
from app.domain.artwork import IMAGE_EXTENSIONS, ArtworkGenerationResult
from app.domain.media import MetadataCandidate, ProviderPerson
from app.domain.nfo import NfoGenerationResult, NfoGenerationSkip, NfoPreviewEntry


@dataclass(frozen=True, slots=True)
class _RemoteArtworkRequest:
    url: str
    directory: Path
    stem: str
    relative_hint: str
    fallback_video: Path | None = None
    fallback_duration: float | None = None


class NfoGenerationService:
    def __init__(
        self,
        catalog: MediaCatalogPort,
        bindings: BindingRepositoryPort,
        provider: MetadataProviderPort | Mapping[str, MetadataProviderPort],
        preview_service: NfoPreviewService,
        media_probe: MediaProbePort,
        artwork_generator: EpisodeArtworkGeneratorPort,
        episode_artwork_fallback_enabled: bool = True,
        operation_mode: str = "nfo_managed_update",
        document_builder: NfoDocumentBuilder | None = None,
        document_merger: NfoDocumentMerger | None = None,
        ignore_marker_manager: IgnoreMarkerPort | None = None,
        remote_artwork_downloader: RemoteArtworkDownloaderPort | None = None,
    ) -> None:
        self._catalog = catalog
        self._bindings = bindings
        self._providers = dict(provider) if isinstance(provider, Mapping) else {"bangumi": provider}
        self._preview_service = preview_service
        self._media_probe = media_probe
        self._artwork_generator = artwork_generator
        self._episode_artwork_fallback_enabled = episode_artwork_fallback_enabled
        self._operation_mode = operation_mode
        self._documents = document_builder or NfoDocumentBuilder()
        self._merger = document_merger or NfoDocumentMerger()
        self._ignore_markers = ignore_marker_manager
        self._remote_artwork = remote_artwork_downloader

    async def generate(
        self,
        media_id: str,
        *,
        confirmed: bool,
        provider: str | None = None,
        bangumi_id: str | None = None,
        tmdb_id: str | None = None,
        season_number: int | None = None,
        episode_offset: int | None = None,
        excluded_paths: tuple[str, ...] = (),
        included_paths: tuple[str, ...] = (),
        overwrite_existing: bool = False,
        locked_fields: tuple[str, ...] = (),
        manual_values: dict[str, object] | None = None,
    ) -> NfoGenerationResult:
        if not confirmed:
            raise NfoGenerationError("CONFIRMATION_REQUIRED", "生成 NFO 前需要明确确认")
        invalid_locks = sorted(
            field for field in set(locked_fields) if not self._merger.supports_lock(field)
        )
        if invalid_locks:
            raise NfoGenerationError(
                "INVALID_NFO_LOCK_FIELD", "包含不支持的 NFO 锁定字段", {"fields": invalid_locks}
            )
        if self._operation_mode == "nfo_create_only":
            overwrite_existing = False
        item = self._catalog.get_media(media_id)
        if item is None:
            raise MediaNotFoundError(media_id)
        if self._ignore_markers is not None:
            self._ignore_markers.synchronize(item.root_path)
        binding = self._bindings.get(media_id)
        configured_season = (
            season_number
            if season_number is not None
            else (binding.season_number if binding else 1)
        )
        selected_provider = self._selected_provider(provider, binding)
        effective_external_id = self._external_id(
            selected_provider, binding, bangumi_id=bangumi_id, tmdb_id=tmdb_id
        )
        if not effective_external_id:
            raise NfoGenerationError(
                "METADATA_NOT_MATCHED", f"请先绑定 {selected_provider.upper()} 条目"
            )
        metadata_provider = self._providers.get(selected_provider)
        if metadata_provider is None:
            raise NfoGenerationError(
                "METADATA_PROVIDER_NOT_SUPPORTED", f"不支持的元数据来源：{selected_provider}"
            )

        provider_season = configured_season
        if selected_provider == "tmdb" and binding:
            configured_provider_season = binding.metadata.get("tmdb_season_number")
            if isinstance(configured_provider_season, int) and not isinstance(
                configured_provider_season, bool
            ):
                provider_season = configured_provider_season
        subject = await metadata_provider.get_subject(effective_external_id)
        episodes = await metadata_provider.get_episodes(effective_external_id, provider_season)
        episode_by_number = {episode.episode_number: episode for episode in episodes}
        offset = (
            episode_offset
            if episode_offset is not None
            else (binding.episode_offset if binding else 0)
        )
        preview = self._preview_service.preview(
            media_id,
            season_number=configured_season,
            episode_offset=offset,
            bangumi_id=effective_external_id,
            bangumi_episode_count=len(episodes),
        )
        excluded = {self._normalize_relative(path) for path in excluded_paths}
        included = {self._normalize_relative(path) for path in included_paths}
        locks = tuple(dict.fromkeys(locked_fields))
        values = manual_values or {}
        documents: dict[Path, str] = {}
        skipped: list[NfoGenerationSkip] = []
        probe_warnings: list[NfoGenerationSkip] = []
        artwork_requests: list[tuple[Path, Path, float | None]] = []
        remote_artwork_requests: list[_RemoteArtworkRequest] = []
        provider_artwork_created: list[Path] = []
        provider_artwork_warnings: list[NfoGenerationSkip] = []

        if (
            self._remote_artwork is not None
            and not self._merger.field_locked("series.artwork", locks)
        ):
            provider_requests: list[_RemoteArtworkRequest] = []
            self._queue_provider_artwork(provider_requests, item.root_path, subject)
            (
                provider_artwork_created,
                provider_artwork_warnings,
                _,
            ) = await self._download_artwork(item.root_path, provider_requests)
            subject = self._localize_provider_artwork(subject, item.root_path)

        series_target = self._safe_target(item.root_path, "tvshow.nfo")
        if not self._merger.field_locked("series.artwork", locks):
            series_urls = self._nfo_artwork_urls(series_target)
            self._queue_remote_artwork(
                remote_artwork_requests,
                subject.image_url or series_urls.get("poster"),
                item.root_path,
                "poster",
                "poster",
                skip=item.poster_path is not None,
            )
            self._queue_remote_artwork(
                remote_artwork_requests,
                subject.fanart_url or series_urls.get("fanart"),
                item.root_path,
                "fanart",
                "fanart",
            )
            self._queue_remote_artwork(
                remote_artwork_requests,
                subject.clearlogo_url or series_urls.get("clearlogo"),
                item.root_path,
                "clearlogo",
                "clearlogo",
            )
        self._queue_document(
            documents,
            skipped,
            series_target,
            "tvshow.nfo",
            self._documents.series(subject, episodes),
            level="series",
            overwrite_existing=overwrite_existing,
            locked_fields=locks,
            manual_values=values,
        )

        season_directories: set[Path] = set()
        for entry in preview.entries:
            if entry.category != "regular" or (
                entry.parsed.episode_start is None and entry.parsed.absolute_episode_start is None
            ):
                continue
            season_directories.add(self._safe_target(item.root_path, entry.folder))
            if not self._selected(entry, excluded, included, overwrite_existing):
                skipped.append(NfoGenerationSkip(entry.target_nfo_relative_path, "NOT_SELECTED"))
                continue
            if entry.action != "create" and not (
                overwrite_existing and entry.action == "unchanged"
            ):
                skipped.append(NfoGenerationSkip(entry.target_nfo_relative_path, "NOT_UPDATEABLE"))
                continue
            mapped_number = (
                entry.parsed.episode_start or entry.parsed.absolute_episode_start or 0
            ) + offset
            provider_episode = episode_by_number.get(mapped_number)
            if provider_episode is None:
                skipped.append(
                    NfoGenerationSkip(entry.target_nfo_relative_path, "PROVIDER_EPISODE_NOT_FOUND")
                )
                continue
            target = self._safe_target(item.root_path, entry.target_nfo_relative_path)
            video_target = self._safe_target(item.root_path, entry.video_relative_path)
            local_episode_number = (
                entry.parsed.episode_start or entry.parsed.absolute_episode_start or mapped_number
            )
            episode_scope = f"{configured_season}:{local_episode_number}"
            media = None
            if not self._merger.field_locked(
                "episodes.media_streams", locks, episode_scope
            ):
                probe_result = await self._media_probe.probe(video_target)
                media = probe_result.media
                if probe_result.warning_code:
                    probe_warnings.append(
                        NfoGenerationSkip(entry.video_relative_path, probe_result.warning_code)
                    )
            artwork_locked = self._merger.field_locked(
                "episodes.artwork", locks, episode_scope
            )
            if not artwork_locked and not self._episode_artwork_exists(video_target):
                episode_image_url = provider_episode.image_url or self._nfo_artwork_urls(
                    target
                ).get("thumb")
                if episode_image_url:
                    relative_hint = video_target.with_name(
                        f"{video_target.stem}-thumb"
                    ).relative_to(item.root_path).as_posix()
                    self._queue_remote_artwork(
                        remote_artwork_requests,
                        episode_image_url,
                        video_target.parent,
                        f"{video_target.stem}-thumb",
                        relative_hint,
                        fallback_video=(
                            video_target if self._episode_artwork_fallback_enabled else None
                        ),
                        fallback_duration=media.duration_seconds if media else None,
                    )
                elif self._episode_artwork_fallback_enabled:
                    artwork_target = video_target.with_name(f"{video_target.stem}-thumb.jpg")
                    artwork_requests.append(
                        (video_target, artwork_target, media.duration_seconds if media else None)
                    )
            self._queue_document(
                documents,
                skipped,
                target,
                entry.target_nfo_relative_path,
                self._documents.episode(
                    provider_episode, configured_season, local_episode_number, media
                ),
                level="episode",
                overwrite_existing=overwrite_existing,
                locked_fields=locks,
                manual_values=values,
            )

        for directory in season_directories:
            season_target = self._safe_child(item.root_path, directory, "season.nfo")
            relative = season_target.relative_to(item.root_path).as_posix()
            season_scope = str(configured_season)
            if not self._merger.field_locked("season.artwork", locks, season_scope):
                season_image_url = next(
                    (
                        episode.season_image_url
                        for episode in episodes
                        if episode.season_image_url
                    ),
                    None,
                ) or self._nfo_artwork_urls(season_target).get("poster") or subject.image_url
                season_stem = (
                    "poster"
                    if directory.resolve(strict=False) != item.root_path.resolve(strict=False)
                    else f"season{configured_season:02}-poster"
                )
                self._queue_remote_artwork(
                    remote_artwork_requests,
                    season_image_url,
                    directory,
                    season_stem,
                    f"{directory.relative_to(item.root_path).as_posix()}/{season_stem}",
                )
            self._queue_document(
                documents,
                skipped,
                season_target,
                relative,
                self._documents.season(subject, episodes, configured_season),
                level="season",
                overwrite_existing=overwrite_existing,
                locked_fields=locks,
                manual_values=values,
            )

        created, updated = self._write_files_atomically(item.root_path, documents)
        remote_created, remote_warnings, remote_fallbacks = await self._download_artwork(
            item.root_path, remote_artwork_requests
        )
        artwork_requests.extend(remote_fallbacks)
        generated_artwork, generated_warnings = await self._generate_artwork(
            item.root_path, artwork_requests
        )
        created_artwork = [
            *provider_artwork_created,
            *remote_created,
            *generated_artwork,
        ]
        artwork_warnings = [
            *provider_artwork_warnings,
            *remote_warnings,
            *generated_warnings,
        ]
        changed = (*created, *updated)
        generated_episode_count = sum(
            path.name.casefold() not in {"tvshow.nfo", "season.nfo"} for path in changed
        )
        return NfoGenerationResult(
            media_id=media_id,
            bangumi_id=effective_external_id,
            created_files=tuple(path.relative_to(item.root_path).as_posix() for path in created),
            skipped_files=tuple(skipped),
            generated_episode_count=generated_episode_count,
            probe_warnings=tuple(probe_warnings),
            updated_files=tuple(path.relative_to(item.root_path).as_posix() for path in updated),
            locked_fields=locks,
            created_artwork_files=tuple(
                path.relative_to(item.root_path).as_posix() for path in created_artwork
            ),
            artwork_warnings=tuple(artwork_warnings),
            provider=selected_provider,
            external_id=effective_external_id,
        )

    @staticmethod
    def _selected_provider(provider: str | None, binding) -> str:
        if provider in {"bangumi", "tmdb"}:
            return provider
        if binding:
            configured = binding.metadata.get("primary_provider")
            if configured in {"bangumi", "tmdb"}:
                return str(configured)
            if binding.tmdb_id and not binding.bangumi_id:
                return "tmdb"
        return "bangumi"

    @staticmethod
    def _external_id(
        provider: str,
        binding,
        *,
        bangumi_id: str | None,
        tmdb_id: str | None,
    ) -> str | None:
        if provider == "tmdb":
            return tmdb_id or (binding.tmdb_id if binding else None)
        return bangumi_id or (binding.bangumi_id if binding else None)

    async def _generate_artwork(
        self,
        root: Path,
        requests: list[tuple[Path, Path, float | None]],
    ) -> tuple[list[Path], list[NfoGenerationSkip]]:
        semaphore = asyncio.Semaphore(2)

        async def generate_one(
            video_path: Path, output_path: Path, duration_seconds: float | None
        ) -> tuple[Path, ArtworkGenerationResult]:
            async with semaphore:
                result = await self._artwork_generator.generate(
                    video_path, output_path, duration_seconds
                )
            return output_path, result

        results = await asyncio.gather(
            *(generate_one(*request) for request in requests),
            return_exceptions=True,
        )
        created: list[Path] = []
        warnings: list[NfoGenerationSkip] = []
        for request, outcome in zip(requests, results, strict=True):
            output_path = request[1]
            relative = output_path.relative_to(root).as_posix()
            if isinstance(outcome, BaseException):
                warnings.append(NfoGenerationSkip(relative, "FFMPEG_CAPTURE_FAILED"))
                continue
            _, result = outcome
            if result.created:
                created.append(output_path)
            if result.warning_code:
                warnings.append(NfoGenerationSkip(relative, result.warning_code))
        return created, warnings

    async def _download_artwork(
        self,
        root: Path,
        requests: list[_RemoteArtworkRequest],
    ) -> tuple[list[Path], list[NfoGenerationSkip], list[tuple[Path, Path, float | None]]]:
        if self._remote_artwork is None:
            fallbacks = [
                (
                    request.fallback_video,
                    request.fallback_video.with_name(f"{request.fallback_video.stem}-thumb.jpg"),
                    request.fallback_duration,
                )
                for request in requests
                if request.fallback_video is not None
            ]
            return [], [], fallbacks

        semaphore = asyncio.Semaphore(4)

        async def download_one(request: _RemoteArtworkRequest):
            async with semaphore:
                return await self._remote_artwork.download(request.url)

        outcomes = await asyncio.gather(
            *(download_one(request) for request in requests),
            return_exceptions=True,
        )
        created: list[Path] = []
        warnings: list[NfoGenerationSkip] = []
        fallbacks: list[tuple[Path, Path, float | None]] = []
        for request, outcome in zip(requests, outcomes, strict=True):
            warning_code: str | None = None
            if isinstance(outcome, BaseException):
                warning_code = "REMOTE_ARTWORK_DOWNLOAD_FAILED"
            elif outcome.warning_code or not outcome.content or not outcome.extension:
                warning_code = outcome.warning_code or "REMOTE_ARTWORK_INVALID"
            else:
                target = request.directory / f"{request.stem}{outcome.extension}"
                try:
                    request.directory.mkdir(parents=True, exist_ok=True)
                    self._ensure_metadata_ignore_marker(root, request.directory)
                    with target.open("xb") as handle:
                        handle.write(outcome.content)
                        handle.flush()
                        os.fsync(handle.fileno())
                except FileExistsError:
                    continue
                except OSError:
                    with suppress(OSError):
                        target.unlink()
                    warning_code = "ARTWORK_WRITE_FAILED"
                else:
                    created.append(target)
                    continue

            warnings.append(NfoGenerationSkip(request.relative_hint, warning_code))
            if request.fallback_video is not None:
                fallbacks.append(
                    (
                        request.fallback_video,
                        request.fallback_video.with_name(
                            f"{request.fallback_video.stem}-thumb.jpg"
                        ),
                        request.fallback_duration,
                    )
                )
        return created, warnings, fallbacks

    def _queue_provider_artwork(self, requests, root: Path, subject) -> None:
        metadata_root = root / ".cymediaflow" / "artwork"
        seen: set[tuple[str, str]] = set()

        def queue(category: str, external_id: str, url: str | None) -> None:
            stem = self._safe_artwork_stem(external_id)
            key = (category, stem)
            if key in seen:
                return
            seen.add(key)
            directory = metadata_root / category
            self._queue_remote_artwork(
                requests,
                url,
                directory,
                stem,
                f".cymediaflow/artwork/{category}/{stem}",
            )

        for person in subject.persons:
            queue("persons", person.external_id, person.image_url)
        for character in subject.characters:
            queue("characters", character.external_id, character.image_url)
            for actor in character.actors:
                queue("voice-actors", actor.external_id, actor.image_url)
        for related in subject.related_subjects:
            queue("related", related.external_id, related.image_url)

    def _localize_provider_artwork(
        self,
        subject: MetadataCandidate,
        root: Path,
    ) -> MetadataCandidate:
        def person(value: ProviderPerson, category: str) -> ProviderPerson:
            return replace(
                value,
                image_url=self._cached_artwork_reference(
                    root, category, value.external_id
                ),
            )

        characters = tuple(
            replace(
                character,
                image_url=self._cached_artwork_reference(
                    root, "characters", character.external_id
                ),
                actors=tuple(person(actor, "voice-actors") for actor in character.actors),
            )
            for character in subject.characters
        )
        related_subjects = tuple(
            replace(
                related,
                image_url=self._cached_artwork_reference(
                    root, "related", related.external_id
                ),
            )
            for related in subject.related_subjects
        )
        return replace(
            subject,
            persons=tuple(person(value, "persons") for value in subject.persons),
            characters=characters,
            related_subjects=related_subjects,
        )

    @staticmethod
    def _cached_artwork_reference(root: Path, category: str, external_id: str) -> str | None:
        directory = root / ".cymediaflow" / "artwork" / category
        stem = NfoGenerationService._safe_artwork_stem(external_id)
        cached = next(
            (
                directory / f"{stem}{extension}"
                for extension in IMAGE_EXTENSIONS
                if (directory / f"{stem}{extension}").is_file()
            ),
            None,
        )
        return cached.relative_to(root).as_posix() if cached is not None else None

    @staticmethod
    def _safe_artwork_stem(value: str) -> str:
        stem = "".join(
            character if character.isalnum() or character in {"-", "_"} else "_"
            for character in value
        ).strip("_")
        return stem[:100] or "unknown"

    @staticmethod
    def _ensure_metadata_ignore_marker(root: Path, directory: Path) -> None:
        try:
            relative = directory.resolve(strict=False).relative_to(root.resolve(strict=False))
        except ValueError:
            return
        if not relative.parts or relative.parts[0].casefold() != ".cymediaflow":
            return
        marker = root / ".cymediaflow" / ".ignore"
        try:
            with marker.open("xb"):
                pass
        except FileExistsError:
            pass

    def _queue_remote_artwork(
        self,
        requests: list[_RemoteArtworkRequest],
        url: str | None,
        directory: Path,
        stem: str,
        relative_hint: str,
        *,
        skip: bool = False,
        fallback_video: Path | None = None,
        fallback_duration: float | None = None,
    ) -> None:
        if skip or not url or self._artwork_stem_exists(directory, stem):
            return
        requests.append(
            _RemoteArtworkRequest(
                url,
                directory,
                stem,
                relative_hint,
                fallback_video,
                fallback_duration,
            )
        )

    @staticmethod
    def _artwork_stem_exists(directory: Path, stem: str) -> bool:
        return any((directory / f"{stem}{extension}").is_file() for extension in IMAGE_EXTENSIONS)

    @staticmethod
    def _episode_artwork_exists(video_path: Path) -> bool:
        return any(
            video_path.with_name(f"{video_path.stem}{suffix}{extension}").is_file()
            for suffix in ("-thumb", ".thumb", "-poster", "")
            for extension in IMAGE_EXTENSIONS
        )

    @staticmethod
    def _nfo_artwork_urls(nfo_path: Path) -> dict[str, str]:
        if not nfo_path.is_file():
            return {}
        try:
            root = ET.fromstring(nfo_path.read_bytes())
        except (ET.ParseError, OSError):
            return {}
        urls: dict[str, str] = {}
        for node in root.findall("thumb"):
            value = (node.text or "").strip()
            if not value.startswith("https://"):
                continue
            aspect = node.attrib.get("aspect", "poster").casefold()
            urls.setdefault("thumb" if root.tag == "episodedetails" else aspect, value)
        fanart = root.find("fanart/thumb")
        fanart_url = (fanart.text or "").strip() if fanart is not None else ""
        if fanart_url.startswith("https://"):
            urls.setdefault("fanart", fanart_url)
        return urls

    def _queue_document(
        self,
        documents: dict[Path, str],
        skipped: list[NfoGenerationSkip],
        target: Path,
        relative: str,
        generated_xml: str,
        *,
        level: str,
        overwrite_existing: bool,
        locked_fields: tuple[str, ...],
        manual_values: dict[str, object],
    ) -> None:
        if not target.exists():
            documents[target] = self._merger.merge(
                generated_xml,
                generated_xml,
                level=level,
                locked_fields=locked_fields,
                manual_values=manual_values,
            )
            return
        if not overwrite_existing:
            skipped.append(NfoGenerationSkip(relative, "ALREADY_EXISTS"))
            return
        try:
            existing_xml = target.read_text(encoding="utf-8-sig")
        except OSError as exc:
            raise NfoGenerationError(
                "NFO_READ_FAILED", "无法读取已有 NFO，已停止覆盖", {"path": relative}
            ) from exc
        documents[target] = self._merger.merge(
            existing_xml,
            generated_xml,
            level=level,
            locked_fields=locked_fields,
            manual_values=manual_values,
        )

    @staticmethod
    def _selected(
        entry: NfoPreviewEntry, excluded: set[str], included: set[str], overwrite_existing: bool
    ) -> bool:
        target = NfoGenerationService._normalize_relative(entry.target_nfo_relative_path)
        if target in included:
            return True
        if target in excluded:
            return False
        return entry.default_selected or (overwrite_existing and entry.action == "unchanged")

    @staticmethod
    def _normalize_relative(value: str) -> str:
        return Path(value.replace("\\", "/")).as_posix().casefold()

    @staticmethod
    def _safe_target(root: Path, relative_path: str) -> Path:
        resolved_root = root.resolve(strict=False)
        target = (resolved_root / Path(relative_path.replace("\\", "/"))).resolve(strict=False)
        try:
            target.relative_to(resolved_root)
        except ValueError as exc:
            raise NfoGenerationError("INVALID_NFO_TARGET", "NFO 目标路径超出媒体目录") from exc
        return target

    @staticmethod
    def _safe_child(root: Path, directory: Path, name: str) -> Path:
        resolved_root = root.resolve(strict=False)
        target = (directory / name).resolve(strict=False)
        try:
            target.relative_to(resolved_root)
        except ValueError as exc:
            raise NfoGenerationError("INVALID_NFO_TARGET", "NFO 目标路径超出媒体目录") from exc
        return target

    @staticmethod
    def _write_files_atomically(
        root: Path, documents: dict[Path, str]
    ) -> tuple[list[Path], list[Path]]:
        created: list[Path] = []
        updated: list[Path] = []
        backups: dict[Path, bytes] = {}
        temporary: set[Path] = set()
        try:
            for path, content in sorted(documents.items(), key=lambda item: item[0].as_posix()):
                path.parent.mkdir(parents=True, exist_ok=True)
                if not path.exists():
                    with path.open("x", encoding="utf-8", newline="\n") as handle:
                        created.append(path)
                        handle.write(content)
                    continue
                backups[path] = path.read_bytes()
                temp = path.with_name(f".{path.name}.cymediaflow-{uuid4().hex}.tmp")
                temporary.add(temp)
                with temp.open("x", encoding="utf-8", newline="\n") as handle:
                    handle.write(content)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temp, path)
                temporary.discard(temp)
                updated.append(path)
        except OSError as exc:
            for path in reversed(created):
                with suppress(OSError):
                    path.unlink()
            for path in reversed(updated):
                with suppress(OSError):
                    rollback = path.with_name(
                        f".{path.name}.cymediaflow-rollback-{uuid4().hex}.tmp"
                    )
                    rollback.write_bytes(backups[path])
                    os.replace(rollback, path)
            for path in temporary:
                with suppress(OSError):
                    path.unlink()
            raise NfoGenerationError(
                "NFO_WRITE_FAILED",
                "NFO 写入失败，本次已创建和覆盖的文件均已回滚",
                {"media_root": str(root)},
            ) from exc
        return created, updated
