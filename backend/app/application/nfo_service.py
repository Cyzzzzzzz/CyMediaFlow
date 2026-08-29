from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path

from app.application.ports import BindingRepositoryPort, MediaCatalogPort
from app.core.errors import MediaNotFoundError
from app.domain.episode_mapping import resolve_episode_mapping, resolve_local_season
from app.domain.filename import ParsedMediaInfo
from app.domain.filename_parser import FilenameParser
from app.domain.media import EpisodeSourceRule
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
        episode_mapping_mode: str | None = None,
        local_episode_number: int | None = None,
        provider_episode_number: int | None = None,
        local_episode_offset: int | None = None,
        overwrite_existing: bool = False,
        bangumi_id: str | None = None,
        bangumi_episode_count: int | None = None,
        episode_source_rules: tuple[EpisodeSourceRule, ...] | None = None,
        excluded_folders: tuple[str, ...] | None = None,
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
        mapping = resolve_episode_mapping(
            mode=episode_mapping_mode,
            local_episode_number=local_episode_number,
            provider_episode_number=provider_episode_number,
            local_episode_offset=local_episode_offset,
            metadata=binding.metadata if binding else None,
        )
        effective_bangumi_id = bangumi_id or (binding.bangumi_id if binding else None)
        effective_episode_count = self._episode_count(
            bangumi_episode_count,
            binding.metadata.get("bangumi_episode_count") if binding else None,
        )
        source_rules = (
            episode_source_rules
            if episode_source_rules is not None
            else (binding.episode_source_rules if binding else ())
        )
        effective_excluded_folders = {
            self._normalize_folder(folder)
            for folder in (
                excluded_folders
                if excluded_folders is not None
                else self._metadata_string_tuple(
                    binding.metadata.get("nfo_excluded_folders") if binding else None
                )
            )
        }
        if mapping.uses_source_rules:
            effective_bangumi_id = effective_bangumi_id or (
                "multi-source" if source_rules else None
            )
            effective_episode_count = None
        preview_offset = 0 if mapping.uses_source_rules else offset

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
        regular_video_count = sum(
            classify_media(relative, parsed) == "regular"
            and not self._folder_is_excluded(
                relative.parent.as_posix(), effective_excluded_folders
            )
            for _, relative, parsed in parsed_videos
        )
        single_mapping_valid = mapping.is_single and regular_video_count == 1
        video_episode_counts = Counter(
            key
            for _, relative, parsed in parsed_videos
            if (
                key := self._episode_key(
                    relative,
                    parsed,
                    configured_season,
                    preview_offset,
                    source_rules=(source_rules if mapping.uses_source_rules else ()),
                    season_override=configured_season if single_mapping_valid else None,
                    episode_override=(
                        mapping.provider_episode_number if single_mapping_valid else None
                    ),
                )
            )
            is not None
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
            episode_key = self._episode_key(
                relative,
                parsed,
                configured_season,
                preview_offset,
                source_rules=(source_rules if mapping.uses_source_rules else ()),
                season_override=configured_season if single_mapping_valid else None,
                episode_override=(
                    mapping.provider_episode_number if single_mapping_valid else None
                ),
            )
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
            parsed_local_episode = self._parsed_episode(parsed)
            parsed_local_season = resolve_local_season(
                relative, parsed.season, configured_season
            )
            source_rule_mapped = not mapping.uses_source_rules or (
                self._matching_source_rule(
                    source_rules,
                    relative.as_posix(),
                    parsed_local_season,
                    parsed_local_episode,
                )
                is not None
            )
            folder_excluded = self._folder_is_excluded(
                relative.parent.as_posix(), effective_excluded_folders
            )
            invalid_local_episode = (
                mapping.adjusts_local_episode
                and parsed_local_episode is not None
                and parsed_local_episode + mapping.local_episode_offset < 0
            )
            selection_reason = self._selection_reason(
                action=action,
                category=category,
                bangumi_id=effective_bangumi_id,
                mapped_episode=mapped_episode,
                bangumi_episode_count=effective_episode_count,
                invalid_single_mapping=mapping.is_single and not single_mapping_valid,
                overwrite_existing=overwrite_existing,
                invalid_local_episode=invalid_local_episode,
                source_rule_mapped=source_rule_mapped,
                folder_excluded=folder_excluded,
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
                    default_selected=(
                        action in {"create", "rename"}
                        or (overwrite_existing and action == "unchanged")
                    )
                    and selection_reason is None,
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
        *,
        source_rules: tuple[EpisodeSourceRule, ...] = (),
        season_override: int | None = None,
        episode_override: int | None = None,
    ) -> tuple[str, int, int] | None:
        if episode_override is not None:
            season = season_override if season_override is not None else configured_season
            return relative_path.parent.as_posix().casefold(), season, episode_override
        episode = NfoPreviewService._parsed_episode(parsed)
        detected_season = resolve_local_season(
            relative_path, parsed.season, configured_season
        )
        source_rule = NfoPreviewService._matching_source_rule(
            source_rules,
            relative_path.as_posix(),
            detected_season,
            episode,
        )
        if source_rule is not None and source_rule.local_path is not None:
            return (
                relative_path.parent.as_posix().casefold(),
                source_rule.local_season,
                source_rule.local_episode_start,
            )
        if episode is None:
            return None
        return (
            relative_path.parent.as_posix().casefold(),
            detected_season,
            episode + offset,
        )

    @staticmethod
    def _matching_source_rule(
        rules: tuple[EpisodeSourceRule, ...],
        relative_path: str,
        local_season: int,
        local_episode: int | None,
    ) -> EpisodeSourceRule | None:
        path_rule = next(
            (
                rule
                for rule in rules
                if rule.local_path is not None
                and rule.matches(relative_path, local_season, local_episode)
            ),
            None,
        )
        if path_rule is not None:
            return path_rule
        return next(
            (
                rule
                for rule in rules
                if rule.local_path is None
                and rule.matches(relative_path, local_season, local_episode)
            ),
            None,
        )

    @staticmethod
    def _parsed_episode(parsed: ParsedMediaInfo) -> int | None:
        if parsed.episode_start is not None:
            return parsed.episode_start
        return parsed.absolute_episode_start

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
        invalid_single_mapping: bool = False,
        overwrite_existing: bool = False,
        invalid_local_episode: bool = False,
        source_rule_mapped: bool = True,
        folder_excluded: bool = False,
    ) -> str | None:
        if invalid_single_mapping:
            return "SINGLE_EPISODE_MAPPING_REQUIRES_ONE_VIDEO"
        if folder_excluded:
            return "FOLDER_EXCLUDED"
        if category != "regular":
            return "NON_BANGUMI_CONTENT"
        if invalid_local_episode:
            return "INVALID_LOCAL_EPISODE_NUMBER"
        if not source_rule_mapped:
            return "EPISODE_SOURCE_NOT_MAPPED"
        if action == "conflict":
            return "TARGET_NFO_CONFLICT"
        if action == "unchanged" and not overwrite_existing:
            return "NFO_ACTION_NOT_REQUIRED"
        if action not in {"create", "rename", "unchanged"}:
            return "NFO_ACTION_NOT_REQUIRED"
        if not bangumi_id:
            return "BANGUMI_NOT_MATCHED"
        if (
            bangumi_episode_count is not None
            and mapped_episode is not None
            and mapped_episode > bangumi_episode_count
        ):
            return "EPISODE_OUTSIDE_BANGUMI_RANGE"
        return None

    @staticmethod
    def _metadata_string_tuple(value: object) -> tuple[str, ...]:
        if not isinstance(value, list):
            return ()
        return tuple(item for item in value if isinstance(item, str))

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
