from __future__ import annotations

from dataclasses import dataclass

from app.domain.media import EpisodeSourceRule


@dataclass(frozen=True, slots=True)
class DetectedEpisodeRange:
    """A local season and its episode numbers detected from immutable video paths."""

    season_number: int
    episode_start: int
    episode_end: int
    episode_count: int


@dataclass(frozen=True, slots=True)
class DetectedSingleFile:
    """An unnumbered main feature that can be represented as an Emby special."""

    relative_path: str
    video_name: str
    suggested_season: int
    suggested_episode: int


@dataclass(frozen=True, slots=True)
class EpisodeMappingSuggestion:
    """Reviewable mapping rules inferred without writing media or NFO files."""

    rules: tuple[EpisodeSourceRule, ...]
    detected_ranges: tuple[DetectedEpisodeRange, ...]
    warnings: tuple[str, ...] = ()
    detected_single_files: tuple[DetectedSingleFile, ...] = ()
