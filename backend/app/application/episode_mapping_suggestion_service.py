from __future__ import annotations

import asyncio
import math
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from app.application.ports import MediaCatalogPort, MetadataProviderPort
from app.core.errors import MediaNotFoundError
from app.domain.episode_mapping import resolve_local_season
from app.domain.filename_parser import FilenameParser
from app.domain.mapping_suggestion import (
    DetectedEpisodeRange,
    DetectedSingleFile,
    EpisodeMappingSuggestion,
)
from app.domain.media import EpisodeSourceRule, ProviderEpisode, ProviderSubjectBinding
from app.domain.media_classification import classify_media

_CHINESE_NUMBERS = {
    "一": 1,
    "二": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
}
_SEASON_HINT_PATTERNS = (
    re.compile(r"第\s*([一二三四五六七八九十\d]+)\s*季", re.IGNORECASE),
    re.compile(r"\bseason\s*0*(\d+)\b", re.IGNORECASE),
)
_EPISODIC_ROLES = {"primary", "season", "season_part"}
_SINGLE_FILE_ROLES = {"movie", "special"}
_MAIN_FILE_PATTERN = re.compile(r"(?:^|[/\\\[\] ._-])main(?:$|[/\\\[\] ._-])", re.I)


@dataclass(frozen=True, slots=True)
class _RemoteEpisodeSet:
    episode_count: int
    first_number: int
    number_mode: str


class EpisodeMappingSuggestionService:
    """Infer safe, reviewable segment rules from local files and provider episodes."""

    def __init__(
        self,
        catalog: MediaCatalogPort,
        providers: dict[str, MetadataProviderPort],
        parser: FilenameParser,
    ) -> None:
        self._catalog = catalog
        self._providers = providers
        self._parser = parser

    async def suggest(
        self,
        media_id: str,
        subjects: tuple[ProviderSubjectBinding, ...],
        default_season: int,
    ) -> EpisodeMappingSuggestion:
        item = self._catalog.get_media(media_id)
        if item is None:
            raise MediaNotFoundError(media_id)

        local_episodes: dict[int, set[int]] = defaultdict(set)
        unnumbered_by_folder: dict[str, list[Path]] = defaultdict(list)
        for path in self._catalog.list_video_files(media_id):
            relative = path.relative_to(item.root_path)
            parsed = self._parser.parse(path.name, parent_directory=item.folder_name)
            if classify_media(relative, parsed) != "regular":
                continue
            episode_start = (
                parsed.episode_start
                if parsed.episode_start is not None
                else parsed.absolute_episode_start
            )
            if episode_start is None:
                unnumbered_by_folder[relative.parent.as_posix()].append(relative)
                continue
            episode_end = parsed.episode_end or parsed.absolute_episode_end or episode_start
            season = resolve_local_season(relative, parsed.season, default_season)
            local_episodes[season].update(range(episode_start, episode_end + 1))

        next_special_episode = max(local_episodes.get(0, {0})) + 1
        single_files: list[DetectedSingleFile] = []
        ambiguous_unnumbered = 0
        for _, paths in sorted(unnumbered_by_folder.items()):
            main_paths = [path for path in paths if _MAIN_FILE_PATTERN.search(path.name)]
            candidates = main_paths if len(main_paths) == 1 else paths if len(paths) == 1 else []
            if not candidates:
                ambiguous_unnumbered += len(paths)
                continue
            relative = candidates[0]
            single_files.append(
                DetectedSingleFile(
                    relative_path=relative.as_posix(),
                    video_name=relative.name,
                    suggested_season=0,
                    suggested_episode=next_special_episode,
                )
            )
            next_special_episode += 1

        ranges = tuple(
            DetectedEpisodeRange(season, min(episodes), max(episodes), len(episodes))
            for season, episodes in sorted(local_episodes.items())
            if episodes
        )
        warnings: list[str] = []
        if ambiguous_unnumbered:
            warnings.append(
                f"有 {ambiguous_unnumbered} 个正片文件未识别出集号，且无法确定唯一主视频。"
            )
        if not ranges and not single_files:
            warnings.append("未从正片文件名或季度目录识别出可映射的季集编号。")
        rules: list[EpisodeSourceRule] = []
        episodic_subjects = tuple(
            subject for subject in subjects if subject.role in _EPISODIC_ROLES
        )
        if ranges and episodic_subjects:
            assignments = self._assign_subjects(episodic_subjects, tuple(local_episodes))
            for season in sorted(local_episodes):
                season_subjects = assignments.get(season, ())
                if not season_subjects:
                    warnings.append(f"本地第 {season} 季没有可推导的来源，需要手动添加规则。")
                    continue
                season_rules, season_warnings = await self._rules_for_season(
                    season,
                    sorted(local_episodes[season]),
                    season_subjects,
                )
                rules.extend(season_rules)
                warnings.extend(season_warnings)
        elif ranges:
            warnings.append("没有可用于常规分集映射的主条目或季度条目。")

        single_subjects = tuple(
            subject for subject in subjects if subject.role in _SINGLE_FILE_ROLES
        )
        if single_files and single_subjects:
            file_rules, file_warnings = await self._rules_for_single_files(
                tuple(single_files), single_subjects
            )
            rules.extend(file_rules)
            warnings.extend(file_warnings)
        elif single_files:
            warnings.append("已发现无集号主视频；请先把对应作品标记为剧场版或特别篇。")
        elif single_subjects:
            warnings.append("已关联剧场版/特别篇条目，但没有识别到可绑定的无集号主视频。")

        return EpisodeMappingSuggestion(
            tuple(rules), ranges, tuple(warnings), tuple(single_files)
        )

    def _assign_subjects(
        self,
        subjects: tuple[ProviderSubjectBinding, ...],
        seasons: tuple[int, ...],
    ) -> dict[int, tuple[ProviderSubjectBinding, ...]]:
        ordered_seasons = tuple(sorted(seasons))
        assigned: dict[int, list[ProviderSubjectBinding]] = defaultdict(list)
        current_index = 0
        for index, subject in enumerate(subjects):
            hinted_season = self._season_hint(subject.title, subject.original_title)
            if hinted_season in ordered_seasons:
                current_index = ordered_seasons.index(hinted_season)
            elif index and subject.role == "season":
                current_index = min(current_index + 1, len(ordered_seasons) - 1)
            assigned[ordered_seasons[current_index]].append(subject)

        # A TMDB TV id normally owns all of its seasons, so reuse it where a local
        # season has no separately associated subject.
        tmdb_fallback = next((subject for subject in subjects if subject.provider == "tmdb"), None)
        if tmdb_fallback is not None:
            for season in ordered_seasons:
                if not assigned[season]:
                    assigned[season].append(tmdb_fallback)
        return {season: tuple(values) for season, values in assigned.items()}

    async def _rules_for_season(
        self,
        season: int,
        local_numbers: list[int],
        subjects: tuple[ProviderSubjectBinding, ...],
    ) -> tuple[list[EpisodeSourceRule], list[str]]:
        requests = []
        for subject in subjects:
            provider = self._providers.get(subject.provider)
            remote_season = season if subject.provider == "tmdb" else 1
            requests.append(
                provider.get_episodes(subject.external_id, remote_season)
                if provider is not None
                else self._missing_provider(subject.provider)
            )
        results = await asyncio.gather(*requests, return_exceptions=True)

        remote_sets: list[_RemoteEpisodeSet | None] = []
        warnings: list[str] = []
        for subject, result in zip(subjects, results, strict=True):
            if isinstance(result, BaseException):
                remote_sets.append(None)
                warnings.append(
                    f"{subject.provider.upper()} #{subject.external_id} 的远程分集读取失败，"
                    "已按本地范围估算。"
                )
                continue
            remote_sets.append(self._remote_episode_set(subject.provider, result))
            if not result:
                warnings.append(
                    f"{subject.provider.upper()} #{subject.external_id} 没有返回分集，"
                    "已按本地范围估算。"
                )

        rules: list[EpisodeSourceRule] = []
        cursor = 0
        for index, (subject, remote_set) in enumerate(
            zip(subjects, remote_sets, strict=True)
        ):
            available = local_numbers[cursor:]
            if not available:
                warnings.append(
                    f"{subject.provider.upper()} #{subject.external_id} 没有剩余本地集数可分配。"
                )
                break
            remaining_sources = len(subjects) - index - 1
            if index == len(subjects) - 1:
                take_count = len(available)
            else:
                desired = remote_set.episode_count if remote_set else math.ceil(
                    len(available) / (remaining_sources + 1)
                )
                take_count = min(max(1, desired), max(1, len(available) - remaining_sources))
            allocated = available[:take_count]
            cursor += take_count
            provider_start = remote_set.first_number if remote_set else 1
            number_mode = remote_set.number_mode if remote_set else (
                "sort" if subject.provider == "bangumi" else "episode"
            )
            rules.append(
                EpisodeSourceRule(
                    provider=subject.provider,
                    external_id=subject.external_id,
                    local_season=season,
                    local_episode_start=allocated[0],
                    local_episode_end=allocated[-1],
                    provider_episode_start=provider_start,
                    provider_season=season if subject.provider == "tmdb" else 1,
                    number_mode=number_mode,
                )
            )
        return rules, warnings

    async def _rules_for_single_files(
        self,
        files: tuple[DetectedSingleFile, ...],
        subjects: tuple[ProviderSubjectBinding, ...],
    ) -> tuple[list[EpisodeSourceRule], list[str]]:
        pair_count = min(len(files), len(subjects))
        requests = []
        for subject in subjects[:pair_count]:
            provider = self._providers.get(subject.provider)
            requests.append(
                provider.get_episodes(subject.external_id, 1)
                if provider is not None
                else self._missing_provider(subject.provider)
            )
        results = await asyncio.gather(*requests, return_exceptions=True)

        rules: list[EpisodeSourceRule] = []
        warnings: list[str] = []
        for detected, subject, result in zip(
            files[:pair_count], subjects[:pair_count], results, strict=True
        ):
            if isinstance(result, BaseException):
                remote_set = None
                warnings.append(
                    f"{subject.provider.upper()} #{subject.external_id} 的远程分集读取失败，"
                    "主视频暂按远程第 1 集映射。"
                )
            else:
                remote_set = self._remote_episode_set(subject.provider, result)
            rules.append(
                EpisodeSourceRule(
                    provider=subject.provider,
                    external_id=subject.external_id,
                    local_season=detected.suggested_season,
                    local_episode_start=detected.suggested_episode,
                    local_episode_end=detected.suggested_episode,
                    provider_episode_start=(remote_set.first_number if remote_set else 1),
                    provider_season=1,
                    number_mode=(
                        remote_set.number_mode
                        if remote_set
                        else "sort" if subject.provider == "bangumi" else "episode"
                    ),
                    local_path=detected.relative_path,
                )
            )
        if len(files) > pair_count:
            warnings.append(f"还有 {len(files) - pair_count} 个主视频没有对应的剧场版/特别篇条目。")
        if len(subjects) > pair_count:
            warnings.append(
                f"还有 {len(subjects) - pair_count} 个剧场版/特别篇条目没有对应主视频。"
            )
        return rules, warnings

    @staticmethod
    async def _missing_provider(provider: str) -> tuple[ProviderEpisode, ...]:
        raise ValueError(f"Unsupported provider: {provider}")

    @staticmethod
    def _remote_episode_set(
        provider: str, episodes: tuple[ProviderEpisode, ...]
    ) -> _RemoteEpisodeSet:
        episode_numbers = sorted({episode.episode_number for episode in episodes})
        if provider == "bangumi":
            sort_numbers = [episode.sort_number for episode in episodes]
            if sort_numbers and all(
                number is not None and float(number).is_integer() for number in sort_numbers
            ):
                normalized = sorted({int(number) for number in sort_numbers if number is not None})
                if normalized:
                    return _RemoteEpisodeSet(len(normalized), normalized[0], "sort")
        return _RemoteEpisodeSet(
            len(episode_numbers),
            episode_numbers[0] if episode_numbers else 1,
            "episode",
        )

    @staticmethod
    def _season_hint(title: str, original_title: str | None) -> int | None:
        value = " ".join(part for part in (title, original_title) if part)
        for pattern in _SEASON_HINT_PATTERNS:
            match = pattern.search(value)
            if not match:
                continue
            raw = match.group(1)
            if raw.isdigit():
                return int(raw)
            return _CHINESE_NUMBERS.get(raw)
        return None
