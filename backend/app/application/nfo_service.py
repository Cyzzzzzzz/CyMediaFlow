from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path

from app.application.ports import BindingRepositoryPort, MediaCatalogPort
from app.core.errors import MediaNotFoundError
from app.domain.filename import ParsedMediaInfo
from app.domain.filename_parser import FilenameParser
from app.domain.media_classification import classify_media
from app.domain.nfo import NfoPreview, NfoPreviewEntry

RESERVED_NFO_NAMES = {"tvshow.nfo", "season.nfo"}


class NfoPreviewService:
    def __init__(
        self,
        catalog: MediaCatalogPort,
        bindings: BindingRepositoryPort,
        parser: FilenameParser,
    ) -> None:
        self._catalog = catalog
        self._bindings = bindings
        self._parser = parser

    def preview(
        self,
        media_id: str,
        *,
        season_number: int | None = None,
        episode_offset: int | None = None,
        bangumi_id: str | None = None,
        bangumi_episode_count: int | None = None,
    ) -> NfoPreview:
        item = self._catalog.get_media(media_id)
        if item is None:
            raise MediaNotFoundError(media_id)
        binding = self._bindings.get(media_id)
        configured_season = (
            season_number
            if season_number is not None
            else (binding.season_number if binding else 1)
        )
        offset = (
            episode_offset
            if episode_offset is not None
            else (binding.episode_offset if binding else 0)
        )
        effective_bangumi_id = bangumi_id or (binding.bangumi_id if binding else None)
        effective_episode_count = self._episode_count(
            bangumi_episode_count,
            binding.metadata.get("bangumi_episode_count") if binding else None,
        )

        videos = self._catalog.list_video_files(media_id)
        nfo_files = self._catalog.list_nfo_files(media_id)
        parsed_videos = [
            (
                path,
                path.relative_to(item.root_path),
                self._parser.parse(path.name, parent_directory=item.folder_name),
            )
            for path in videos
        ]
        video_episode_counts = Counter(
            key
            for _, relative, parsed in parsed_videos
            if (key := self._episode_key(relative, parsed, configured_season, offset)) is not None
        )
        nfo_by_path = {
            path.relative_to(item.root_path).as_posix().casefold(): path for path in nfo_files
        }
        target_keys = {
            path.relative_to(item.root_path).with_suffix(".nfo").as_posix().casefold()
            for path in videos
        }
        alternative_nfos: dict[tuple[str, int, int], list[Path]] = defaultdict(list)
        for nfo_path in nfo_files:
            relative = nfo_path.relative_to(item.root_path)
            if relative.name.casefold() in RESERVED_NFO_NAMES:
                continue
            if relative.as_posix().casefold() in target_keys:
                continue
            parsed = self._parser.parse(nfo_path.name, parent_directory=item.folder_name)
            key = self._episode_key(relative, parsed, configured_season, 0)
            if key is not None:
                alternative_nfos[key].append(nfo_path)

        target_counts = Counter(
            path.relative_to(item.root_path).with_suffix(".nfo").as_posix().casefold()
            for path in videos
        )
        entries: list[NfoPreviewEntry] = []
        for _, relative, parsed in parsed_videos:
            category = classify_media(relative, parsed)
            target_relative = relative.with_suffix(".nfo")
            target_key = target_relative.as_posix().casefold()
            warnings = list(parsed.warnings)
            if category != "regular":
                warnings.append("NON_BANGUMI_CONTENT")

            source_nfo: Path | None = nfo_by_path.get(target_key)
            candidates: list[Path] = []
            episode_key = self._episode_key(relative, parsed, configured_season, offset)
            if source_nfo is not None:
                action = "unchanged"
            elif target_counts[target_key] > 1:
                action = "conflict"
                warnings.append("TARGET_NFO_CONFLICT")
            elif episode_key is None:
                action = "review"
                warnings.append("EPISODE_NOT_FOUND")
            else:
                candidates = alternative_nfos.get(episode_key, [])
                if len(candidates) == 1 and video_episode_counts[episode_key] == 1:
                    source_nfo = candidates[0]
                    action = "rename"
                elif candidates:
                    action = "conflict"
                    warnings.append("AMBIGUOUS_NFO_PAIRING")
                else:
                    action = "create"

            mapped_episode = episode_key[2] if episode_key else None
            selection_reason = self._selection_reason(
                action=action,
                category=category,
                bangumi_id=effective_bangumi_id,
                mapped_episode=mapped_episode,
                bangumi_episode_count=effective_episode_count,
            )
            if selection_reason and selection_reason not in warnings:
                warnings.append(selection_reason)
            source_relative = source_nfo.relative_to(item.root_path) if source_nfo else None
            entries.append(
                NfoPreviewEntry(
                    video_relative_path=relative.as_posix(),
                    video_name=relative.name,
                    source_nfo_relative_path=(
                        source_relative.as_posix() if source_relative else None
                    ),
                    source_nfo_name=source_relative.name if source_relative else None,
                    target_nfo_relative_path=target_relative.as_posix(),
                    target_nfo_name=target_relative.name,
                    action=action,
                    folder=relative.parent.as_posix(),
                    category=category,
                    default_selected=action in {"create", "rename"} and selection_reason is None,
                    selection_reason=selection_reason,
                    parsed=parsed,
                    warnings=tuple(warnings),
                )
            )

        counts = Counter(entry.action for entry in entries)
        selected_count = sum(entry.default_selected for entry in entries)
        return NfoPreview(
            media_id=media_id,
            operation_mode="read_only_preview",
            total=len(entries),
            create_count=counts["create"],
            rename_count=counts["rename"],
            unchanged_count=counts["unchanged"],
            review_count=counts["review"],
            conflict_count=counts["conflict"],
            default_selected_count=selected_count,
            default_skipped_count=len(entries) - selected_count,
            entries=tuple(entries),
        )

    @staticmethod
    def _episode_key(
        relative_path: Path,
        parsed: ParsedMediaInfo,
        configured_season: int,
        offset: int,
    ) -> tuple[str, int, int] | None:
        episode = parsed.episode_start or parsed.absolute_episode_start
        if episode is None:
            return None
        season = parsed.season if parsed.season is not None else configured_season
        return relative_path.parent.as_posix().casefold(), season, episode + offset

    @staticmethod
    def _episode_count(request_value: int | None, stored_value: object) -> int | None:
        if request_value is not None:
            return request_value
        if isinstance(stored_value, int) and not isinstance(stored_value, bool):
            return stored_value
        return None

    @staticmethod
    def _selection_reason(
        *,
        action: str,
        category: str,
        bangumi_id: str | None,
        mapped_episode: int | None,
        bangumi_episode_count: int | None,
    ) -> str | None:
        if action == "conflict":
            return "TARGET_NFO_CONFLICT"
        if action not in {"create", "rename"}:
            return "NFO_ACTION_NOT_REQUIRED"
        if category != "regular":
            return "NON_BANGUMI_CONTENT"
        if not bangumi_id:
            return "BANGUMI_NOT_MATCHED"
        if (
            bangumi_episode_count is not None
            and mapped_episode is not None
            and mapped_episode > bangumi_episode_count
        ):
            return "EPISODE_OUTSIDE_BANGUMI_RANGE"
        return None
