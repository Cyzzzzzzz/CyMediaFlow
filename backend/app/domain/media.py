from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ExternalIdentity:
    provider: str
    external_id: str


@dataclass(frozen=True, slots=True)
class MediaItem:
    id: str
    folder_name: str
    title: str
    year: int | None
    root_path: Path
    added_at: datetime
    poster_path: Path | None
    video_count: int
    seasons: tuple[int, ...]
    external_ids: tuple[ExternalIdentity, ...] = ()
    nfo_present: bool = False


@dataclass(frozen=True, slots=True)
class ProviderInfoboxValue:
    value: str
    label: str | None = None


@dataclass(frozen=True, slots=True)
class ProviderInfoboxItem:
    key: str
    values: tuple[ProviderInfoboxValue, ...]


@dataclass(frozen=True, slots=True)
class ProviderRating:
    score: float | None
    rank: int | None
    total: int
    distribution: tuple[tuple[int, int], ...] = ()


@dataclass(frozen=True, slots=True)
class ProviderTag:
    name: str
    count: int = 0
    total_count: int = 0


@dataclass(frozen=True, slots=True)
class ProviderPerson:
    external_id: str
    name: str
    relation: str | None = None
    career: tuple[str, ...] = ()
    episode_scope: str | None = None
    image_url: str | None = None


@dataclass(frozen=True, slots=True)
class ProviderCharacter:
    external_id: str
    name: str
    relation: str
    summary: str | None = None
    image_url: str | None = None
    actors: tuple[ProviderPerson, ...] = ()
    infobox: tuple[ProviderInfoboxItem, ...] = ()
    birth_year: int | None = None
    birth_month: int | None = None
    birth_day: int | None = None
    gender: str | None = None
    blood_type: str | None = None


@dataclass(frozen=True, slots=True)
class ProviderRelatedSubject:
    external_id: str
    name: str
    title: str | None
    relation: str
    subject_type: int | None = None
    image_url: str | None = None


@dataclass(frozen=True, slots=True)
class MetadataCandidate:
    provider: str
    external_id: str
    title: str
    original_title: str | None
    year: int | None
    episode_count: int | None
    image_url: str | None
    summary: str | None
    premiere_date: str | None = None
    platform: str | None = None
    total_episode_count: int | None = None
    infobox: tuple[ProviderInfoboxItem, ...] = ()
    rating: ProviderRating | None = None
    meta_tags: tuple[str, ...] = ()
    tags: tuple[ProviderTag, ...] = ()
    persons: tuple[ProviderPerson, ...] = ()
    characters: tuple[ProviderCharacter, ...] = ()
    fanart_url: str | None = None
    clearlogo_url: str | None = None
    related_subjects: tuple[ProviderRelatedSubject, ...] = ()


@dataclass(frozen=True, slots=True)
class ProviderEpisode:
    external_id: str
    episode_number: int
    title: str
    original_title: str | None
    air_date: str | None
    summary: str | None
    runtime_minutes: int | None
    subject_id: str | None = None
    episode_type: int = 0
    sort_number: float | None = None
    disc_number: int | None = None
    comment_count: int = 0
    duration_text: str | None = None
    duration_seconds: int | None = None
    image_url: str | None = None
    provider: str = "bangumi"
    season_image_url: str | None = None


@dataclass(frozen=True, slots=True)
class ScrapeBinding:
    media_id: str
    bangumi_id: str | None = None
    tmdb_id: str | None = None
    preferred_title: str | None = None
    content_kind: str = "series"
    year: int | None = None
    season_number: int = 1
    episode_offset: int = 0
    folder_template: str = "{title} ({year})/Season {season:02}"
    filename_template: str = "{title} S{season:02}E{episode:02}"
    emby_enabled: bool = True
    image_url: str | None = None
    metadata: dict[str, object] = field(default_factory=dict)
