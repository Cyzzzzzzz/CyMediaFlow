from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping
from dataclasses import asdict, dataclass, replace
from datetime import date, datetime, time

from app.application.nfo_generation_service import NfoGenerationService
from app.application.ports import (
    BindingRepositoryPort,
    MetadataProviderPort,
    ResultCachePort,
)
from app.core.errors import DomainError
from app.domain.media import (
    MetadataCandidate,
    ProviderEpisode,
    ScheduledRefresh,
    ScrapeBinding,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class _SourceReference:
    provider: str
    external_id: str
    provider_season: int
    track_broadcast: bool = False


@dataclass(frozen=True, slots=True)
class _BroadcastProgress:
    current_episode: int | None = None
    total_episodes: int | None = None
    final_air_date: str | None = None
    complete: bool = False
    failed_sources: int = 0


class ScheduledRefreshService:
    """Runs persisted per-work refreshes without an external scheduler dependency."""

    def __init__(
        self,
        bindings: BindingRepositoryPort,
        providers: Mapping[str, MetadataProviderPort],
        nfo_generation: NfoGenerationService,
        result_cache: ResultCachePort,
        *,
        poll_seconds: float = 30.0,
    ) -> None:
        self._bindings = bindings
        self._providers = dict(providers)
        self._nfo_generation = nfo_generation
        self._result_cache = result_cache
        self._poll_seconds = max(1.0, poll_seconds)
        self._stop_event = asyncio.Event()
        self._task: asyncio.Task[None] | None = None
        self._locks: dict[str, asyncio.Lock] = {}

    async def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run_loop(), name="cymediaflow-scheduled-refresh")

    async def stop(self) -> None:
        task = self._task
        if task is None:
            return
        self._stop_event.set()
        await task
        self._task = None

    async def run_due(self, now: datetime | None = None) -> tuple[str, ...]:
        local_now = now or datetime.now().astimezone()
        completed: list[str] = []
        for media_id, binding in self._bindings.list_all().items():
            if not self._is_due(binding.scheduled_refresh, local_now):
                continue
            try:
                await self.run_media(media_id, now=local_now)
            except DomainError as exc:
                logger.warning(
                    "Scheduled work %s was skipped: %s (%s)",
                    media_id,
                    exc.message,
                    exc.code,
                )
                continue
            completed.append(media_id)
        return tuple(completed)

    async def run_media(
        self,
        media_id: str,
        *,
        now: datetime | None = None,
    ) -> ScheduledRefresh:
        local_now = now or datetime.now().astimezone()
        lock = self._locks.setdefault(media_id, asyncio.Lock())
        async with lock:
            binding = self._bindings.get(media_id)
            if binding is None:
                raise DomainError(
                    code="SCRAPE_CONFIG_REQUIRED",
                    message="请先保存番剧的刮削配置",
                    status_code=409,
                    details={"media_id": media_id},
                )
            try:
                progress, preloaded_sources = await self._refresh_remote_cache_and_progress(
                    media_id, binding, local_now.date()
                )
            except Exception:
                logger.exception(
                    "Could not update remote cache/progress before refreshing %s",
                    media_id,
                )
                progress = _BroadcastProgress(failed_sources=1)
                preloaded_sources = {}
            try:
                result = await self._nfo_generation.generate(
                    media_id,
                    confirmed=True,
                    provider=self._primary_provider(binding),
                    bangumi_id=binding.bangumi_id,
                    tmdb_id=binding.tmdb_id,
                    season_number=binding.season_number,
                    episode_offset=binding.episode_offset,
                    episode_mapping_mode=self._mapping_mode(binding),
                    local_episode_number=self._metadata_int(binding, "nfo_local_episode_number", 1),
                    provider_episode_number=self._metadata_int(
                        binding, "nfo_provider_episode_number", 1
                    ),
                    local_episode_offset=self._metadata_int(binding, "nfo_local_episode_offset", 0),
                    excluded_paths=self._metadata_strings(binding, "nfo_excluded_paths"),
                    excluded_folders=self._metadata_strings(binding, "nfo_excluded_folders"),
                    included_paths=self._metadata_strings(binding, "nfo_included_paths"),
                    overwrite_existing=True,
                    locked_fields=self._metadata_strings(binding, "nfo_locked_fields"),
                    manual_values=self._metadata_dict(binding, "nfo_manual_values"),
                    preloaded_sources=preloaded_sources,
                )
            except DomainError as exc:
                schedule = replace(
                    binding.scheduled_refresh,
                    last_run_at=local_now.isoformat(),
                    last_status="failed",
                    last_message=exc.message,
                )
                self._bindings.upsert(replace(binding, scheduled_refresh=schedule))
                logger.warning(
                    "Scheduled refresh failed for %s: %s (%s)",
                    media_id,
                    exc.message,
                    exc.code,
                )
                return schedule
            except Exception:
                schedule = replace(
                    binding.scheduled_refresh,
                    last_run_at=local_now.isoformat(),
                    last_status="failed",
                    last_message="定时刷新失败，请查看后端日志",
                )
                self._bindings.upsert(replace(binding, scheduled_refresh=schedule))
                logger.exception("Unexpected scheduled refresh failure for %s", media_id)
                return schedule

            changed_count = len(result.created_files) + len(result.updated_files)
            if progress.complete:
                message = (
                    f"已完成最终更新：Bangumi "
                    f"{progress.current_episode}/{progress.total_episodes}，定时刷新已停止"
                )
                schedule = replace(
                    binding.scheduled_refresh,
                    enabled=False,
                    last_run_at=local_now.isoformat(),
                    last_status="completed",
                    last_message=message,
                    current_episode=progress.current_episode,
                    total_episodes=progress.total_episodes,
                    final_air_date=progress.final_air_date,
                )
            else:
                progress_text = self._progress_text(progress)
                message = f"NFO 刷新成功，写入或更新 {changed_count} 个文件"
                if progress_text:
                    message = f"{message}；{progress_text}"
                schedule = replace(
                    binding.scheduled_refresh,
                    last_run_at=local_now.isoformat(),
                    last_status="success",
                    last_message=message,
                    current_episode=progress.current_episode,
                    total_episodes=progress.total_episodes,
                    final_air_date=progress.final_air_date,
                )
            self._bindings.upsert(replace(binding, scheduled_refresh=schedule))
            try:
                self._result_cache.delete(media_id, ("scrape-info", "nfo-preview"))
            except Exception:
                logger.exception("Could not invalidate local result cache for %s", media_id)
            return schedule

    async def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                await self.run_due()
            except Exception:
                logger.exception("Scheduled refresh polling failed")
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self._poll_seconds)
            except asyncio.TimeoutError:
                continue

    @staticmethod
    def _is_due(schedule: ScheduledRefresh, now: datetime) -> bool:
        if not schedule.enabled:
            return False
        try:
            due_time = time.fromisoformat(schedule.daily_time)
        except ValueError:
            return False
        if now.timetz().replace(tzinfo=None) < due_time:
            return False
        if not schedule.last_run_at:
            return True
        try:
            last_run = datetime.fromisoformat(schedule.last_run_at)
        except ValueError:
            return True
        if last_run.tzinfo is None:
            last_run = last_run.replace(tzinfo=now.tzinfo)
        return last_run.astimezone(now.tzinfo).date() < now.date()

    async def _refresh_remote_cache_and_progress(
        self,
        media_id: str,
        binding: ScrapeBinding,
        today: date,
    ) -> tuple[
        _BroadcastProgress,
        dict[
            tuple[str, str, int],
            tuple[MetadataCandidate, tuple[ProviderEpisode, ...]],
        ],
    ]:
        references = self._source_references(binding)
        outcomes = await asyncio.gather(
            *(self._load_source(reference) for reference in references),
            return_exceptions=True,
        )
        current_total = 0
        episode_total = 0
        final_dates: list[date] = []
        tracked = failed = complete_count = 0
        preloaded_sources: dict[
            tuple[str, str, int],
            tuple[MetadataCandidate, tuple[ProviderEpisode, ...]],
        ] = {}
        for reference, outcome in zip(references, outcomes, strict=True):
            if isinstance(outcome, BaseException):
                if reference.track_broadcast:
                    tracked += 1
                    failed += 1
                logger.warning(
                    "Could not refresh scheduled source %s:%s for %s",
                    reference.provider,
                    reference.external_id,
                    media_id,
                )
                continue
            subject, episodes = outcome
            preloaded_sources[
                (
                    reference.provider,
                    reference.external_id,
                    reference.provider_season,
                )
            ] = (subject, episodes)
            try:
                self._cache_source(media_id, reference, subject, episodes)
            except Exception:
                logger.exception(
                    "Could not persist refreshed source cache %s:%s for %s",
                    reference.provider,
                    reference.external_id,
                    media_id,
                )
            if not reference.track_broadcast or reference.provider != "bangumi":
                continue
            tracked += 1
            subject_progress = self._subject_progress(subject, episodes, today)
            if subject_progress.current_episode is not None:
                current_total += subject_progress.current_episode
            if subject_progress.total_episodes is not None:
                episode_total += subject_progress.total_episodes
            if subject_progress.final_air_date:
                final_dates.append(date.fromisoformat(subject_progress.final_air_date))
            if subject_progress.complete:
                complete_count += 1
        return (
            _BroadcastProgress(
                current_episode=current_total if tracked and not failed else None,
                total_episodes=(
                    episode_total if tracked and not failed and episode_total else None
                ),
                final_air_date=max(final_dates).isoformat() if final_dates else None,
                complete=tracked > 0 and not failed and complete_count == tracked,
                failed_sources=failed,
            ),
            preloaded_sources,
        )

    async def _load_source(
        self, reference: _SourceReference
    ) -> tuple[MetadataCandidate, tuple[ProviderEpisode, ...]]:
        provider = self._providers[reference.provider]
        subject, episodes = await asyncio.gather(
            provider.get_subject(reference.external_id),
            provider.get_episodes(reference.external_id, reference.provider_season),
        )
        return subject, episodes

    def _cache_source(
        self,
        media_id: str,
        reference: _SourceReference,
        subject: MetadataCandidate,
        episodes: tuple[ProviderEpisode, ...],
    ) -> None:
        self._result_cache.put(
            media_id,
            "metadata-detail",
            asdict(subject),
            {"external_id": reference.external_id, "provider": reference.provider},
        )
        self._result_cache.put(
            media_id,
            "metadata-episodes",
            [asdict(episode) for episode in episodes],
            {
                "external_id": reference.external_id,
                "provider": reference.provider,
                "season_number": reference.provider_season,
            },
        )

    @staticmethod
    def _subject_progress(
        subject: MetadataCandidate,
        episodes: tuple[ProviderEpisode, ...],
        today: date,
    ) -> _BroadcastProgress:
        regular = tuple(episode for episode in episodes if episode.episode_type == 0)
        total = subject.total_episode_count or subject.episode_count
        aired = tuple(
            episode
            for episode in regular
            if (air_date := ScheduledRefreshService._episode_date(episode)) is not None
            and air_date <= today
        )
        current = max((episode.episode_number for episode in aired), default=0)
        final_episode = next(
            (
                episode
                for episode in regular
                if total is not None and episode.episode_number == total
            ),
            None,
        )
        final_date = (
            ScheduledRefreshService._episode_date(final_episode)
            if final_episode is not None
            else None
        )
        complete = bool(
            total and current >= total and final_date is not None and final_date < today
        )
        return _BroadcastProgress(
            current_episode=current,
            total_episodes=total,
            final_air_date=final_date.isoformat() if final_date else None,
            complete=complete,
        )

    @staticmethod
    def _episode_date(episode: ProviderEpisode | None) -> date | None:
        if episode is None or not episode.air_date:
            return None
        try:
            return date.fromisoformat(episode.air_date)
        except ValueError:
            return None

    @classmethod
    def _source_references(cls, binding: ScrapeBinding) -> tuple[_SourceReference, ...]:
        primary_provider = cls._primary_provider(binding)
        primary_id = binding.tmdb_id if primary_provider == "tmdb" else binding.bangumi_id
        primary_season = binding.season_number
        if primary_provider == "tmdb":
            primary_season = cls._metadata_int(binding, "tmdb_season_number", primary_season)
        references: dict[tuple[str, str, int], _SourceReference] = {}
        if primary_id:
            key = (primary_provider, primary_id, primary_season)
            references[key] = _SourceReference(*key, track_broadcast=primary_provider == "bangumi")
        if cls._mapping_mode(binding) == "segments":
            for rule in binding.episode_source_rules:
                key = (rule.provider, rule.external_id, rule.provider_season)
                track = rule.provider == "bangumi" and rule.local_path is None
                existing = references.get(key)
                references[key] = _SourceReference(
                    *key,
                    track_broadcast=track or bool(existing and existing.track_broadcast),
                )
        return tuple(references.values())

    @staticmethod
    def _primary_provider(binding: ScrapeBinding) -> str:
        configured = binding.metadata.get("primary_provider")
        if configured in {"bangumi", "tmdb"}:
            return str(configured)
        if binding.tmdb_id and not binding.bangumi_id:
            return "tmdb"
        return "bangumi"

    @staticmethod
    def _mapping_mode(binding: ScrapeBinding) -> str:
        value = binding.metadata.get("nfo_episode_mapping_mode")
        return value if value in {"manual", "single", "segments"} else "auto"

    @staticmethod
    def _metadata_int(binding: ScrapeBinding, key: str, fallback: int) -> int:
        value = binding.metadata.get(key)
        return value if isinstance(value, int) and not isinstance(value, bool) else fallback

    @staticmethod
    def _metadata_strings(binding: ScrapeBinding, key: str) -> tuple[str, ...]:
        value = binding.metadata.get(key)
        if not isinstance(value, list | tuple):
            return ()
        return tuple(item for item in value if isinstance(item, str))

    @staticmethod
    def _metadata_dict(binding: ScrapeBinding, key: str) -> dict[str, object]:
        value = binding.metadata.get(key)
        return dict(value) if isinstance(value, dict) else {}

    @staticmethod
    def _progress_text(progress: _BroadcastProgress) -> str | None:
        if progress.failed_sources:
            return "Bangumi 放送进度暂时无法确认"
        if progress.current_episode is None or progress.total_episodes is None:
            return "当前来源不支持自动判断完结"
        return f"Bangumi 已播 {progress.current_episode}/{progress.total_episodes}"
