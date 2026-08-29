from __future__ import annotations

from dataclasses import dataclass, field, replace
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
class ProviderSubjectBinding:
    """One remote subject associated with a local library work."""

    provider: str
    external_id: str
    title: str
    original_title: str | None = None
    image_url: str | None = None
    role: str = "season_part"


@dataclass(frozen=True, slots=True)
class EpisodeSourceRule:
    """Maps a local episode range or one immutable video path to a remote subject."""

    provider: str
    external_id: str
    local_season: int
    local_episode_start: int
    local_episode_end: int | None = None
    provider_episode_start: int = 1
    provider_season: int = 1
    number_mode: str = "episode"
    local_path: str | None = None

    def contains(self, season: int, episode: int) -> bool:
        return (
            season == self.local_season
            and episode >= self.local_episode_start
            and (self.local_episode_end is None or episode <= self.local_episode_end)
        )

    def provider_episode_number(self, local_episode: int) -> int:
        return self.provider_episode_start + local_episode - self.local_episode_start

    def matches(
        self,
        relative_path: str,
        season: int,
        episode: int | None,
    ) -> bool:
        """Prefer an exact path binding; otherwise use the legacy numeric range."""

        if self.local_path is not None:
            return self._normalize_path(relative_path) == self._normalize_path(self.local_path)
        return episode is not None and self.contains(season, episode)

    @staticmethod
    def _normalize_path(value: str) -> str:
        return value.replace("\\", "/").strip("/").casefold()


@dataclass(frozen=True, slots=True)
class ScheduledRefresh:
    """Per-work daily metadata/NFO refresh configuration and last-run state."""

    enabled: bool = False
    daily_time: str = "04:00"
    last_run_at: str | None = None
    last_status: str = "never"
    last_message: str | None = None
    current_episode: int | None = None
    total_episodes: int | None = None
    final_air_date: str | None = None


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
    provider_subjects: tuple[ProviderSubjectBinding, ...] = ()
    episode_source_rules: tuple[EpisodeSourceRule, ...] = ()
    scheduled_refresh: ScheduledRefresh = field(default_factory=ScheduledRefresh)


def normalize_primary_binding(binding: ScrapeBinding) -> ScrapeBinding:
    """Return a binding whose primary provider always points at a real subject.

    Older UI versions could leave ``primary_provider`` set to TMDB after the TMDB
    tab was merely viewed, even when the work only contained Bangumi subjects.
    Keep the invariant in the domain layer so reads and NFO generation cannot use
    that stale provider value.
    """

    metadata = dict(binding.metadata)
    configured_provider = metadata.get("primary_provider")
    configured_provider = (
        configured_provider
        if configured_provider in {"bangumi", "tmdb"}
        else None
    )
    subjects = binding.provider_subjects

    if not subjects:
        valid_provider = None
        if configured_provider == "bangumi" and binding.bangumi_id:
            valid_provider = "bangumi"
        elif configured_provider == "tmdb" and binding.tmdb_id:
            valid_provider = "tmdb"
        elif binding.bangumi_id:
            valid_provider = "bangumi"
        elif binding.tmdb_id:
            valid_provider = "tmdb"
        if valid_provider:
            metadata["primary_provider"] = valid_provider
        else:
            metadata.pop("primary_provider", None)
        return replace(binding, metadata=metadata)

    explicit_primaries = [subject for subject in subjects if subject.role == "primary"]
    primary = explicit_primaries[0] if len(explicit_primaries) == 1 else None
    if primary is None and configured_provider:
        configured_id = (
            binding.tmdb_id if configured_provider == "tmdb" else binding.bangumi_id
        )
        if configured_id:
            primary = next(
                (
                    subject
                    for subject in subjects
                    if subject.provider == configured_provider
                    and subject.external_id == configured_id
                ),
                None,
            )
    if primary is None and explicit_primaries:
        primary = explicit_primaries[0]
    if primary is None:
        for provider, external_id in (
            ("bangumi", binding.bangumi_id),
            ("tmdb", binding.tmdb_id),
        ):
            if not external_id:
                continue
            primary = next(
                (
                    subject
                    for subject in subjects
                    if subject.provider == provider and subject.external_id == external_id
                ),
                None,
            )
            if primary is not None:
                break
    if primary is None:
        primary = subjects[0]

    primary_key = (primary.provider, primary.external_id)
    normalized_subjects = tuple(
        replace(
            subject,
            role=(
                "primary"
                if (subject.provider, subject.external_id) == primary_key
                else "season_part"
                if subject.role == "primary"
                else subject.role
            ),
        )
        for subject in subjects
    )
    metadata["primary_provider"] = primary.provider
    return replace(
        binding,
        bangumi_id=(
            primary.external_id if primary.provider == "bangumi" else binding.bangumi_id
        ),
        tmdb_id=(primary.external_id if primary.provider == "tmdb" else binding.tmdb_id),
        metadata=metadata,
        provider_subjects=normalized_subjects,
    )
