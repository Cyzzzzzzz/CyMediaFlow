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
from app.domain.episode_mapping import resolve_episode_mapping, resolve_local_season
from app.domain.media import (
    EpisodeSourceRule,
    MetadataCandidate,
    ProviderEpisode,
    ProviderPerson,
)
from app.domain.nfo import NfoGenerationResult, NfoGenerationSkip, NfoPreviewEntry


@dataclass(frozen=True, slots=True)
class _RemoteArtworkRequest:
    url: str
    directory: Path
    stem: str
    relative_hint: str
    fallback_video: Path | None = None
    fallback_duration: float | None = None
    overwrite_existing: bool = False


@dataclass(frozen=True, slots=True)
class _LoadedSource:
    provider: str
    external_id: str
    provider_season: int
    subject: MetadataCandidate
    episodes: tuple[ProviderEpisode, ...]


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
        episode_mapping_mode: str | None = None,
        local_episode_number: int | None = None,
        provider_episode_number: int | None = None,
        local_episode_offset: int | None = None,
        excluded_paths: tuple[str, ...] = (),
        excluded_folders: tuple[str, ...] = (),
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
        primary_source = await self._load_source(
            selected_provider, effective_external_id, provider_season
        )
        subject = primary_source.subject
        episodes = primary_source.episodes
        source_cache = {
            self._source_key(selected_provider, effective_external_id, provider_season): (
                primary_source
            )
        }
        source_rules = binding.episode_source_rules if binding else ()
        if mapping.uses_source_rules:
            if not source_rules:
                raise NfoGenerationError(
                    "EPISODE_SOURCE_RULES_REQUIRED",
                    "多条目分段模式至少需要一条季度/分集来源规则",
                )
            requested_sources = {
                self._source_key(rule.provider, rule.external_id, rule.provider_season)
                for rule in source_rules
            }
            missing_sources = [
                source_key
                for source_key in requested_sources
                if source_key not in source_cache
            ]
            loaded_sources = await asyncio.gather(
                *(self._load_source(*source_key) for source_key in missing_sources)
            )
            source_cache.update(
                {
                    self._source_key(
                        loaded.provider, loaded.external_id, loaded.provider_season
                    ): loaded
                    for loaded in loaded_sources
                }
            )
        episode_by_number: dict[int, ProviderEpisode] = {}
        for episode in episodes:
            current = episode_by_number.get(episode.episode_number)
            if current is None or (
                current.episode_type != 0 and episode.episode_type == 0
            ):
                episode_by_number[episode.episode_number] = episode
        excluded = {self._normalize_relative(path) for path in excluded_paths}
        configured_excluded_folders = excluded_folders or self._metadata_string_tuple(
            binding.metadata.get("nfo_excluded_folders") if binding else None
        )
        excluded_folder_set = {
            self._normalize_folder(folder) for folder in configured_excluded_folders
        }
        included = {self._normalize_relative(path) for path in included_paths}
        preview = self._preview_service.preview(
            media_id,
            season_number=configured_season,
            episode_offset=offset,
            episode_mapping_mode=mapping.mode,
            local_episode_number=mapping.local_episode_number,
            provider_episode_number=mapping.provider_episode_number,
            local_episode_offset=mapping.local_episode_offset,
            overwrite_existing=overwrite_existing,
            bangumi_id=effective_external_id,
            bangumi_episode_count=(None if mapping.uses_source_rules else len(episodes)),
            episode_source_rules=source_rules,
            excluded_folders=configured_excluded_folders,
        )
        regular_entries = [
            entry
            for entry in preview.entries
            if entry.category == "regular"
            and not self._folder_is_excluded(entry.folder, excluded_folder_set)
        ]
        if mapping.is_single and len(regular_entries) != 1:
            raise NfoGenerationError(
                "SINGLE_EPISODE_MAPPING_REQUIRES_ONE_VIDEO",
                "单文件剧场版/特别篇映射要求目录内恰好有一个常规视频文件",
                {"regular_video_count": len(regular_entries)},
            )
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
            self._documents.series(
                subject,
                episodes,
                binding.provider_subjects if binding else (),
            ),
            level="series",
            overwrite_existing=overwrite_existing,
            locked_fields=locks,
            manual_values=values,
        )

        season_directories: dict[Path, int] = {}
        season_sources: dict[int, list[_LoadedSource]] = {}
        for entry in preview.entries:
            if entry.category != "regular":
                continue
            parsed_episode = self._parsed_episode(entry)
            detected_local_season = resolve_local_season(
                entry.video_relative_path,
                entry.parsed.season,
                configured_season,
            )
            source_rule = (
                self._matching_source_rule(
                    source_rules,
                    entry.video_relative_path,
                    detected_local_season,
                    parsed_episode,
                )
                if mapping.uses_source_rules
                else None
            )
            if (
                not mapping.is_single
                and parsed_episode is None
                and source_rule is None
            ):
                skipped.append(
                    NfoGenerationSkip(
                        entry.target_nfo_relative_path,
                        "LOCAL_EPISODE_NOT_RECOGNIZED",
                    )
                )
                continue
            local_season = configured_season
            if mapping.uses_source_rules:
                local_season = (
                    source_rule.local_season
                    if source_rule is not None
                    else detected_local_season
                )
            if not self._selected(
                entry, excluded, excluded_folder_set, included, overwrite_existing
            ):
                reason = (
                    "EPISODE_SOURCE_NOT_MAPPED"
                    if mapping.uses_source_rules
                    and entry.selection_reason == "EPISODE_SOURCE_NOT_MAPPED"
                    else "NOT_SELECTED"
                )
                skipped.append(NfoGenerationSkip(entry.target_nfo_relative_path, reason))
                continue
            if entry.action != "create" and not (
                overwrite_existing and entry.action == "unchanged"
            ):
                skipped.append(NfoGenerationSkip(entry.target_nfo_relative_path, "NOT_UPDATEABLE"))
                continue
            loaded_source = primary_source
            if mapping.uses_source_rules:
                if source_rule is None:
                    skipped.append(
                        NfoGenerationSkip(
                            entry.target_nfo_relative_path, "EPISODE_SOURCE_NOT_MAPPED"
                        )
                    )
                    continue
                source_key = self._source_key(
                    source_rule.provider,
                    source_rule.external_id,
                    source_rule.provider_season,
                )
                loaded_source = source_cache[source_key]
                if source_rule.local_path is not None:
                    mapped_number = source_rule.provider_episode_start
                elif parsed_episode is not None:
                    mapped_number = source_rule.provider_episode_number(parsed_episode)
                else:
                    skipped.append(
                        NfoGenerationSkip(
                            entry.target_nfo_relative_path,
                            "LOCAL_EPISODE_NOT_RECOGNIZED",
                        )
                    )
                    continue
                provider_episode = self._find_provider_episode(
                    loaded_source.episodes, mapped_number, source_rule.number_mode
                )
            else:
                mapped_number = (
                    mapping.provider_episode_number
                    if mapping.is_single
                    else (parsed_episode or 0) + offset
                )
                provider_episode = episode_by_number.get(mapped_number)
            if provider_episode is None:
                skipped.append(
                    NfoGenerationSkip(entry.target_nfo_relative_path, "PROVIDER_EPISODE_NOT_FOUND")
                )
                continue
            target = self._safe_target(item.root_path, entry.target_nfo_relative_path)
            video_target = self._safe_target(item.root_path, entry.video_relative_path)
            if mapping.is_single:
                effective_local_episode = mapping.local_episode_number
            elif source_rule is not None and source_rule.local_path is not None:
                effective_local_episode = source_rule.local_episode_start
            else:
                effective_local_episode = (parsed_episode or 0) + (
                    mapping.local_episode_offset if mapping.adjusts_local_episode else 0
                )
            if effective_local_episode < 0:
                skipped.append(
                    NfoGenerationSkip(
                        entry.target_nfo_relative_path, "INVALID_LOCAL_EPISODE_NUMBER"
                    )
                )
                continue
            effective_local_season = configured_season if mapping.is_single else local_season
            episode_scope = f"{effective_local_season}:{effective_local_episode}"
            season_directories[
                self._safe_target(item.root_path, entry.folder)
            ] = effective_local_season
            season_sources.setdefault(effective_local_season, [])
            if loaded_source not in season_sources[effective_local_season]:
                season_sources[effective_local_season].append(loaded_source)
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
            if not artwork_locked and not self._episode_artwork_exists(
                video_target, target, item.root_path
            ):
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
                    )
                elif (
                    self._episode_artwork_fallback_enabled
                    and not self._fallback_preview_exists(
                        item.root_path,
                        video_target.parent,
                        effective_local_season,
                        item.poster_path,
                    )
                ):
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
                    provider_episode,
                    effective_local_season,
                    effective_local_episode,
                    media,
                ),
                level="episode",
                overwrite_existing=overwrite_existing,
                locked_fields=locks,
                manual_values=values,
            )

        for directory, local_season in season_directories.items():
            season_target = self._safe_child(item.root_path, directory, "season.nfo")
            relative = season_target.relative_to(item.root_path).as_posix()
            season_scope = str(local_season)
            sources_for_season = season_sources.get(local_season) or [primary_source]
            season_source = sources_for_season[0]
            season_subject = season_source.subject
            season_episodes = tuple(
                episode
                for source in sources_for_season
                for episode in source.episodes
            )
            if not self._merger.field_locked("season.artwork", locks, season_scope):
                season_image_url = next(
                    (
                        episode.season_image_url
                        for episode in season_episodes
                        if episode.season_image_url
                    ),
                    None,
                ) or self._nfo_artwork_urls(season_target).get("poster") or season_subject.image_url
                directory_is_root = (
                    directory.resolve(strict=False) == item.root_path.resolve(strict=False)
                )
                season_stem = (
                    f"season{local_season:02}-poster" if directory_is_root else "poster"
                )
                self._queue_remote_artwork(
                    remote_artwork_requests,
                    season_image_url,
                    directory,
                    season_stem,
                    f"{directory.relative_to(item.root_path).as_posix()}/{season_stem}",
                    overwrite_existing=overwrite_existing,
                )
                if not directory_is_root:
                    root_stem = f"season{local_season:02}-poster"
                    self._queue_remote_artwork(
                        remote_artwork_requests,
                        season_image_url,
                        item.root_path,
                        root_stem,
                        root_stem,
                        overwrite_existing=overwrite_existing,
                    )
            self._queue_document(
                documents,
                skipped,
                season_target,
                relative,
                self._documents.season(
                    season_subject,
                    season_episodes,
                    local_season,
                    tuple(
                        subject_binding
                        for subject_binding in (binding.provider_subjects if binding else ())
                        if any(
                            source.provider == subject_binding.provider
                            and source.external_id == subject_binding.external_id
                            for source in sources_for_season
                        )
                    ),
                ),
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

    @staticmethod
    def _source_key(provider: str, external_id: str, provider_season: int) -> tuple[str, str, int]:
        return provider, external_id, provider_season

    async def _load_source(
        self, provider: str, external_id: str, provider_season: int
    ) -> _LoadedSource:
        metadata_provider = self._providers.get(provider)
        if metadata_provider is None:
            raise NfoGenerationError(
                "METADATA_PROVIDER_NOT_SUPPORTED",
                f"不支持的元数据来源：{provider}",
            )
        subject, episodes = await asyncio.gather(
            metadata_provider.get_subject(external_id),
            metadata_provider.get_episodes(external_id, provider_season),
        )
        return _LoadedSource(provider, external_id, provider_season, subject, episodes)

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
    def _find_provider_episode(
        episodes: tuple[ProviderEpisode, ...], number: int, number_mode: str
    ) -> ProviderEpisode | None:
        if number_mode == "sort":
            matches = tuple(
                episode
                for episode in episodes
                if episode.sort_number is not None
                and abs(episode.sort_number - number) < 0.0001
            )
            return min(
                matches,
                key=lambda episode: (
                    0 if episode.episode_type == 0 else 1,
                    episode.episode_number,
                ),
                default=None,
            )
        return next(
            (episode for episode in episodes if episode.episode_number == number),
            None,
        )

    @staticmethod
    def _parsed_episode(entry: NfoPreviewEntry) -> int | None:
        if entry.parsed.episode_start is not None:
            return entry.parsed.episode_start
        if entry.parsed.absolute_episode_start is not None:
            return entry.parsed.absolute_episode_start
        return None

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
                temporary = request.directory / (
                    f".{request.stem}.{uuid4().hex}{outcome.extension}.tmp"
                )
                try:
                    request.directory.mkdir(parents=True, exist_ok=True)
                    self._ensure_metadata_ignore_marker(root, request.directory)
                    write_target = temporary if request.overwrite_existing else target
                    with write_target.open("xb") as handle:
                        handle.write(outcome.content)
                        handle.flush()
                        os.fsync(handle.fileno())
                    if request.overwrite_existing:
                        os.replace(temporary, target)
                        for extension in IMAGE_EXTENSIONS:
                            alternate = request.directory / f"{request.stem}{extension}"
                            if alternate != target:
                                with suppress(OSError):
                                    alternate.unlink()
                except FileExistsError:
                    continue
                except OSError:
                    with suppress(OSError):
                        temporary.unlink()
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
        overwrite_existing: bool = False,
    ) -> None:
        if (
            skip
            or not url
            or any(request.directory == directory and request.stem == stem for request in requests)
            or (not overwrite_existing and self._artwork_stem_exists(directory, stem))
        ):
            return
        requests.append(
            _RemoteArtworkRequest(
                url,
                directory,
                stem,
                relative_hint,
                fallback_video,
                fallback_duration,
                overwrite_existing,
            )
        )

    @staticmethod
    def _artwork_stem_exists(directory: Path, stem: str) -> bool:
        return any((directory / f"{stem}{extension}").is_file() for extension in IMAGE_EXTENSIONS)

    @classmethod
    def _episode_artwork_exists(
        cls,
        video_path: Path,
        nfo_path: Path | None = None,
        media_root: Path | None = None,
    ) -> bool:
        if any(
            video_path.with_name(f"{video_path.stem}{suffix}{extension}").is_file()
            for suffix in ("-thumb", ".thumb", "-poster", "")
            for extension in IMAGE_EXTENSIONS
        ):
            return True
        if nfo_path is None or media_root is None or not nfo_path.is_file():
            return False
        try:
            root = ET.fromstring(nfo_path.read_bytes())
        except (ET.ParseError, OSError):
            return False
        resolved_media_root = media_root.resolve(strict=False)
        for node in root.findall("thumb"):
            value = (node.text or "").strip()
            if not value or "://" in value:
                continue
            reference = Path(value.replace("\\", "/"))
            candidates = (
                (reference,)
                if reference.is_absolute()
                else (nfo_path.parent / reference, resolved_media_root / reference)
            )
            for candidate in candidates:
                resolved = candidate.resolve(strict=False)
                try:
                    resolved.relative_to(resolved_media_root)
                except ValueError:
                    continue
                if resolved.suffix.casefold() in IMAGE_EXTENSIONS and resolved.is_file():
                    return True
        return False

    @classmethod
    def _fallback_preview_exists(
        cls,
        media_root: Path,
        episode_directory: Path,
        season_number: int,
        series_poster: Path | None,
    ) -> bool:
        if series_poster is not None and series_poster.is_file():
            return True
        candidates = (
            (episode_directory, f"season{season_number:02}-poster"),
            (episode_directory, "season-poster"),
            (episode_directory, "poster"),
            (episode_directory, "folder"),
            (media_root, f"season{season_number:02}-poster"),
            (media_root, f"season{season_number}-poster"),
        )
        return any(cls._artwork_stem_exists(directory, stem) for directory, stem in candidates)

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
        entry: NfoPreviewEntry,
        excluded: set[str],
        excluded_folders: set[str],
        included: set[str],
        overwrite_existing: bool,
    ) -> bool:
        target = NfoGenerationService._normalize_relative(entry.target_nfo_relative_path)
        if NfoGenerationService._folder_is_excluded(entry.folder, excluded_folders):
            return False
        if target in included:
            return True
        if target in excluded:
            return False
        return entry.default_selected or (overwrite_existing and entry.action == "unchanged")

    @staticmethod
    def _normalize_relative(value: str) -> str:
        return Path(value.replace("\\", "/")).as_posix().casefold()

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
