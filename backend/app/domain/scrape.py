from __future__ import annotations

from dataclasses import dataclass

from app.domain.media import ExternalIdentity


@dataclass(frozen=True, slots=True)
class SeriesScrapeInfo:
    title: str
    original_title: str | None
    plot: str | None
    year: int | None
    premiered: str | None
    end_date: str | None
    status: str | None
    rating: float | None
    runtime: int | None
    genres: tuple[str, ...]
    tags: tuple[str, ...]
    studios: tuple[str, ...]
    cast: tuple[str, ...]
    directors: tuple[str, ...]
    writers: tuple[str, ...]
    external_ids: tuple[ExternalIdentity, ...]
    artwork: tuple[str, ...]
    provider_data: str | None
    poster_source: str


@dataclass(frozen=True, slots=True)
class EpisodeScrapeInfo:
    season_number: int
    episode_number: int
    title: str
    original_title: str | None
    plot: str | None
    aired: str | None
    runtime: int | None
    external_ids: tuple[ExternalIdentity, ...]
    artwork: tuple[str, ...]
    provider_data: str | None
    media_streams: str | None
    nfo_relative_path: str
    poster_source: str


@dataclass(frozen=True, slots=True)
class SeasonScrapeInfo:
    season_number: int
    title: str | None
    original_title: str | None
    plot: str | None
    year: int | None
    premiered: str | None
    cast: tuple[str, ...]
    external_ids: tuple[ExternalIdentity, ...]
    artwork: tuple[str, ...]
    provider_data: str | None
    nfo_relative_path: str | None
    poster_source: str
    episodes: tuple[EpisodeScrapeInfo, ...]


@dataclass(frozen=True, slots=True)
class LocalScrapeInfo:
    media_id: str
    series: SeriesScrapeInfo | None
    seasons: tuple[SeasonScrapeInfo, ...]
