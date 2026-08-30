from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SubtitleMatchEntry:
    source_relative_path: str
    source_name: str
    target_relative_path: str | None
    target_name: str | None
    video_relative_path: str | None
    video_name: str | None
    folder: str
    season_number: int | None
    episode_number: int | None
    language: str | None
    language_tag: str | None
    status: str
    default_selected: bool
    reason: str | None
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SubtitleMatchPreview:
    media_id: str
    operation_mode: str
    total: int
    rename_count: int
    unchanged_count: int
    review_count: int
    conflict_count: int
    default_selected_count: int
    entries: tuple[SubtitleMatchEntry, ...]


@dataclass(frozen=True, slots=True)
class SubtitleRenameOperation:
    source_relative_path: str
    target_relative_path: str


@dataclass(frozen=True, slots=True)
class SubtitleRenameSkip:
    relative_path: str
    reason: str


@dataclass(frozen=True, slots=True)
class SubtitleRenameResult:
    media_id: str
    renamed_files: tuple[SubtitleRenameOperation, ...]
    skipped_files: tuple[SubtitleRenameSkip, ...]
