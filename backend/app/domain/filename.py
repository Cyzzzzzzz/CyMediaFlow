from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class FileRole(str, Enum):
    VIDEO = "video"
    SUBTITLE = "subtitle"
    OTHER = "other"

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class ParseTraceStep:
    stage: str
    value: str
    detail: str


@dataclass(frozen=True, slots=True)
class ParsedMediaInfo:
    raw_filename: str
    stem: str
    extension: str
    file_role: FileRole
    title: str | None
    title_candidates: tuple[str, ...]
    year: int | None
    season: int | None
    episode_start: int | None
    episode_end: int | None
    absolute_episode_start: int | None
    absolute_episode_end: int | None
    special_type: str | None
    special_number: int | None
    release_group: str | None
    resolution: str | None
    source: str | None
    video_codec: str | None
    audio_codec: str | None
    bit_depth: int | None
    version: int | None
    subtitle_language: str | None
    subtitle_flags: frozenset[str]
    matched_rule_id: str | None
    confidence: float
    warnings: tuple[str, ...]
    trace: tuple[ParseTraceStep, ...]


@dataclass(frozen=True, slots=True)
class NamingPreviewEntry:
    source_relative_path: str
    target_relative_path: str
    source_name: str
    target_name: str
    status: str
    folder: str
    category: str
    default_selected: bool
    selection_reason: str | None
    parsed: ParsedMediaInfo
    warnings: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class NamingPreview:
    media_id: str
    operation_mode: str
    total: int
    rename_count: int
    unchanged_count: int
    review_count: int
    conflict_count: int
    default_selected_count: int
    default_skipped_count: int
    entries: tuple[NamingPreviewEntry, ...]
