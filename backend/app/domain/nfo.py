from __future__ import annotations

from dataclasses import dataclass

from app.domain.filename import ParsedMediaInfo


@dataclass(frozen=True, slots=True)
class NfoPreviewEntry:
    video_relative_path: str
    video_name: str
    source_nfo_relative_path: str | None
    source_nfo_name: str | None
    target_nfo_relative_path: str
    target_nfo_name: str
    action: str
    folder: str
    category: str
    default_selected: bool
    selection_reason: str | None
    parsed: ParsedMediaInfo
    warnings: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class NfoPreview:
    media_id: str
    operation_mode: str
    total: int
    create_count: int
    rename_count: int
    unchanged_count: int
    review_count: int
    conflict_count: int
    default_selected_count: int
    default_skipped_count: int
    entries: tuple[NfoPreviewEntry, ...]


@dataclass(frozen=True, slots=True)
class NfoGenerationSkip:
    relative_path: str
    reason: str


@dataclass(frozen=True, slots=True)
class NfoGenerationResult:
    media_id: str
    bangumi_id: str
    created_files: tuple[str, ...]
    skipped_files: tuple[NfoGenerationSkip, ...]
    generated_episode_count: int
    probe_warnings: tuple[NfoGenerationSkip, ...] = ()
    updated_files: tuple[str, ...] = ()
    locked_fields: tuple[str, ...] = ()
    created_artwork_files: tuple[str, ...] = ()
    artwork_warnings: tuple[NfoGenerationSkip, ...] = ()
    provider: str = "bangumi"
    external_id: str | None = None
