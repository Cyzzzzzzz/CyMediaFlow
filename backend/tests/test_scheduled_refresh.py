from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.application.scheduled_refresh_service import ScheduledRefreshService
from app.domain.media import (
    MetadataCandidate,
    ProviderEpisode,
    ProviderSubjectBinding,
    ScheduledRefresh,
    ScrapeBinding,
)


class MemoryBindings:
    def __init__(self, binding: ScrapeBinding) -> None:
        self.data = {binding.media_id: binding}

    def get(self, media_id: str) -> ScrapeBinding | None:
        return self.data.get(media_id)

    def list_all(self) -> dict[str, ScrapeBinding]:
        return dict(self.data)

    def upsert(self, binding: ScrapeBinding) -> ScrapeBinding:
        self.data[binding.media_id] = binding
        return binding


class MemoryCache:
    def __init__(self) -> None:
        self.entries: list[tuple[str, str, object, object]] = []
        self.deleted: list[tuple[str, tuple[str, ...]]] = []

    def put(self, media_id, category, payload, parameters=None) -> None:
        self.entries.append((media_id, category, payload, parameters))

    def delete(self, media_id, categories=None) -> None:
        self.deleted.append((media_id, tuple(categories or ())))


class BangumiProgressProvider:
    configured = True

    def __init__(self) -> None:
        self.subject = MetadataCandidate(
            provider="bangumi",
            external_id="501963",
            title="无职转生 第三季",
            original_title=None,
            year=2026,
            episode_count=14,
            image_url=None,
            summary=None,
            total_episode_count=14,
        )
        dates = [
            "2026-07-04",
            "2026-07-04",
            "2026-07-12",
            "2026-07-19",
            "2026-07-26",
            "2026-08-02",
            "2026-08-09",
            "2026-08-16",
            "2026-08-23",
            "2026-08-30",
            "2026-09-06",
            "2026-09-13",
            "2026-09-20",
            "2026-09-27",
        ]
        self.episodes = tuple(
            ProviderEpisode(
                external_id=str(1_704_815 + number),
                episode_number=number,
                title=f"Episode {number}",
                original_title=None,
                air_date=air_date,
                summary=None,
                runtime_minutes=24,
                subject_id="501963",
                episode_type=0,
                sort_number=float(number),
            )
            for number, air_date in enumerate(dates, start=1)
        )

    async def get_subject(self, _external_id: str) -> MetadataCandidate:
        return self.subject

    async def get_episodes(
        self, _external_id: str, _season_number: int
    ) -> tuple[ProviderEpisode, ...]:
        return self.episodes


def scheduled_binding() -> ScrapeBinding:
    return ScrapeBinding(
        media_id="work-1",
        bangumi_id="501963",
        metadata={
            "primary_provider": "bangumi",
            "nfo_excluded_paths": ["Season 1/skip.nfo"],
            "nfo_excluded_folders": ["SPs"],
            "nfo_included_paths": ["Season 1/include.nfo"],
            "nfo_locked_fields": ["series.title"],
            "nfo_manual_values": {"series.title": "Locked title"},
        },
        provider_subjects=(
            ProviderSubjectBinding(
                provider="bangumi",
                external_id="501963",
                title="无职转生 第三季",
                role="primary",
            ),
        ),
        scheduled_refresh=ScheduledRefresh(enabled=True, daily_time="04:00"),
    )


@pytest.mark.asyncio
async def test_scheduled_refresh_tracks_current_bangumi_episode_and_reuses_config() -> None:
    bindings = MemoryBindings(scheduled_binding())
    provider = BangumiProgressProvider()
    nfo_generation = SimpleNamespace(
        generate=AsyncMock(
            return_value=SimpleNamespace(
                created_files=("tvshow.nfo",), updated_files=("Season 1/episode.nfo",)
            )
        )
    )
    cache = MemoryCache()
    service = ScheduledRefreshService(bindings, {"bangumi": provider}, nfo_generation, cache)

    schedule = await service.run_media(
        "work-1", now=datetime.fromisoformat("2026-08-30T05:00:00+08:00")
    )

    assert schedule.enabled is True
    assert schedule.last_status == "success"
    assert schedule.current_episode == 10
    assert schedule.total_episodes == 14
    assert schedule.final_air_date == "2026-09-27"
    assert "Bangumi 已播 10/14" in (schedule.last_message or "")
    kwargs = nfo_generation.generate.await_args.kwargs
    assert kwargs["provider"] == "bangumi"
    assert kwargs["overwrite_existing"] is True
    assert kwargs["excluded_folders"] == ("SPs",)
    assert kwargs["locked_fields"] == ("series.title",)
    assert kwargs["manual_values"] == {"series.title": "Locked title"}
    assert ("bangumi", "501963", 1) in kwargs["preloaded_sources"]
    assert {entry[1] for entry in cache.entries} == {
        "metadata-detail",
        "metadata-episodes",
    }
    assert cache.deleted == [("work-1", ("scrape-info", "nfo-preview"))]


@pytest.mark.asyncio
async def test_scheduled_refresh_stops_after_safe_post_final_episode_update() -> None:
    bindings = MemoryBindings(scheduled_binding())
    provider = BangumiProgressProvider()
    nfo_generation = SimpleNamespace(
        generate=AsyncMock(
            return_value=SimpleNamespace(created_files=(), updated_files=("tvshow.nfo",))
        )
    )
    service = ScheduledRefreshService(
        bindings, {"bangumi": provider}, nfo_generation, MemoryCache()
    )

    on_final_date = await service.run_media(
        "work-1", now=datetime.fromisoformat("2026-09-27T05:00:00+08:00")
    )
    completed = await service.run_media(
        "work-1", now=datetime.fromisoformat("2026-09-28T05:00:00+08:00")
    )

    assert on_final_date.enabled is True
    assert on_final_date.current_episode == 14
    assert completed.enabled is False
    assert completed.last_status == "completed"
    assert "14/14" in (completed.last_message or "")
    assert nfo_generation.generate.await_count == 2


@pytest.mark.asyncio
async def test_due_scheduler_runs_each_work_only_once_per_local_day() -> None:
    bindings = MemoryBindings(scheduled_binding())
    nfo_generation = SimpleNamespace(
        generate=AsyncMock(return_value=SimpleNamespace(created_files=(), updated_files=()))
    )
    service = ScheduledRefreshService(
        bindings,
        {"bangumi": BangumiProgressProvider()},
        nfo_generation,
        MemoryCache(),
    )
    now = datetime.fromisoformat("2026-08-30T05:00:00+08:00")

    first = await service.run_due(now)
    second = await service.run_due(now)

    assert first == ("work-1",)
    assert second == ()
    assert nfo_generation.generate.await_count == 1
