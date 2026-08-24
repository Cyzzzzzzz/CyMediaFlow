from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from app.application.ports import BindingRepositoryPort, MediaCatalogPort
from app.core.errors import MediaNotFoundError
from app.domain.filename import NamingPreview, NamingPreviewEntry, ParsedMediaInfo
from app.domain.filename_parser import FilenameParser
from app.domain.media_classification import classify_media

INVALID_FILENAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
ALLOWED_TEMPLATE_FIELDS = {"title", "season", "episode", "episode_end", "absolute_episode"}


class NamingPreviewService:
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
        preferred_title: str | None = None,
        season_number: int | None = None,
        episode_offset: int | None = None,
        filename_template: str | None = None,
        bangumi_id: str | None = None,
        bangumi_episode_count: int | None = None,
    ) -> NamingPreview:
        item = self._catalog.get_media(media_id)
        if item is None:
            raise MediaNotFoundError(media_id)
        binding = self._bindings.get(media_id)
        effective_bangumi_id = bangumi_id or (binding.bangumi_id if binding else None)
        effective_episode_count = self._episode_count(
            bangumi_episode_count,
            binding.metadata.get("bangumi_episode_count") if binding else None,
        )
        title = self._safe_title(
            preferred_title
            or (binding.preferred_title if binding else None)
            or item.title
            or item.folder_name
        )
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
        template = filename_template or (
            binding.filename_template if binding else "{title} S{season:02}E{episode:02}"
        )
        files = self._catalog.list_video_files(media_id)
        parsed_files = [
            (path, self._parser.parse(path.name, parent_directory=item.folder_name))
            for path in files
        ]

        drafts: list[_Draft] = []
        for path, parsed in parsed_files:
            warnings = list(parsed.warnings)
            source_relative = path.relative_to(item.root_path)
            category = classify_media(source_relative, parsed)
            if category != "regular":
                warnings.append("NON_BANGUMI_CONTENT")
            episode = parsed.episode_start or parsed.absolute_episode_start or parsed.special_number
            episode_end = parsed.episode_end or parsed.absolute_episode_end or episode
            if episode is None:
                drafts.append(
                    _Draft(source_relative, path.name, tuple(warnings), parsed, category, None)
                )
                continue
            mapped_episode = episode + offset
            mapped_end = (episode_end + offset) if episode_end is not None else mapped_episode
            if mapped_episode < 0 or mapped_end < mapped_episode:
                warnings.append("EPISODE_MAPPING_OUT_OF_RANGE")
                drafts.append(
                    _Draft(
                        source_relative,
                        path.name,
                        tuple(warnings),
                        parsed,
                        category,
                        mapped_episode,
                    )
                )
                continue
            season = parsed.season if parsed.season is not None else configured_season
            try:
                target_stem = template.format_map(
                    _StrictTemplateValues(
                        title=title,
                        season=season,
                        episode=mapped_episode,
                        episode_end=mapped_end,
                        absolute_episode=parsed.absolute_episode_start or mapped_episode,
                    )
                )
            except (KeyError, ValueError):
                warnings.append("INVALID_FILENAME_TEMPLATE")
                drafts.append(
                    _Draft(
                        source_relative,
                        path.name,
                        tuple(warnings),
                        parsed,
                        category,
                        mapped_episode,
                    )
                )
                continue
            target_stem = self._safe_title(target_stem)
            target_name = f"{target_stem}{parsed.extension}"
            drafts.append(
                _Draft(
                    source_relative,
                    target_name,
                    tuple(warnings),
                    parsed,
                    category,
                    mapped_episode,
                )
            )

        target_counts = Counter(
            str(draft.source.parent / draft.target_name).casefold() for draft in drafts
        )
        source_paths = {str(path.relative_to(item.root_path)).casefold() for path in files}
        entries: list[NamingPreviewEntry] = []
        for draft in drafts:
            source_relative = draft.source
            target_name = draft.target_name
            warnings = draft.warnings
            parsed = draft.parsed
            target_relative = source_relative.parent / target_name
            target_key = str(target_relative).casefold()
            source_key = str(source_relative).casefold()
            collision = target_counts[target_key] > 1 or (
                target_key in source_paths and target_key != source_key
            )
            if collision:
                status = "conflict"
                warnings = (*warnings, "TARGET_PATH_CONFLICT")
            elif "INVALID_FILENAME_TEMPLATE" in warnings or all(
                value is None
                for value in (
                    parsed.episode_start,
                    parsed.absolute_episode_start,
                    parsed.special_number,
                )
            ):
                status = "review"
            elif source_relative.name == target_name:
                status = "unchanged"
            else:
                status = "rename"
            selection_reason = self._selection_reason(
                status=status,
                category=draft.category,
                bangumi_id=effective_bangumi_id,
                mapped_episode=draft.mapped_episode,
                bangumi_episode_count=effective_episode_count,
            )
            if selection_reason and selection_reason not in warnings:
                warnings = (*warnings, selection_reason)
            default_selected = status == "rename" and selection_reason is None
            entries.append(
                NamingPreviewEntry(
                    source_relative_path=source_relative.as_posix(),
                    target_relative_path=target_relative.as_posix(),
                    source_name=source_relative.name,
                    target_name=target_name,
                    status=status,
                    folder=source_relative.parent.as_posix(),
                    category=draft.category,
                    default_selected=default_selected,
                    selection_reason=selection_reason,
                    parsed=parsed,
                    warnings=warnings,
                )
            )

        status_counts = Counter(entry.status for entry in entries)
        default_selected_count = sum(entry.default_selected for entry in entries)
        return NamingPreview(
            media_id=media_id,
            operation_mode="read_only_preview",
            total=len(entries),
            rename_count=status_counts["rename"],
            unchanged_count=status_counts["unchanged"],
            review_count=status_counts["review"],
            conflict_count=status_counts["conflict"],
            default_selected_count=default_selected_count,
            default_skipped_count=len(entries) - default_selected_count,
            entries=tuple(entries),
        )

    @staticmethod
    def _safe_title(value: str) -> str:
        value = INVALID_FILENAME.sub(" ", value)
        value = re.sub(r"\s+", " ", value).strip(" .")
        return value or "Untitled"

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
        status: str,
        category: str,
        bangumi_id: str | None,
        mapped_episode: int | None,
        bangumi_episode_count: int | None,
    ) -> str | None:
        if status == "conflict":
            return "TARGET_PATH_CONFLICT"
        if status != "rename":
            return "NOT_A_RENAME"
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


@dataclass(frozen=True, slots=True)
class _Draft:
    source: Path
    target_name: str
    warnings: tuple[str, ...]
    parsed: ParsedMediaInfo
    category: str
    mapped_episode: int | None


class _StrictTemplateValues(dict[str, object]):
    def __init__(self, **values: object) -> None:
        unknown = set(values) - ALLOWED_TEMPLATE_FIELDS
        if unknown:
            raise KeyError(next(iter(unknown)))
        super().__init__(values)

    def __missing__(self, key: str) -> object:
        raise KeyError(key)
