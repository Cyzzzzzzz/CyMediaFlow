from __future__ import annotations

from dataclasses import dataclass

from app.domain.media import ScrapeBinding


@dataclass(frozen=True, slots=True)
class EpisodeFileRenameOperation:
    source_relative_path: str
    target_relative_path: str
    kind: str


@dataclass(frozen=True, slots=True)
class EpisodeFileRenameSkip:
    relative_path: str
    reason: str


@dataclass(frozen=True, slots=True)
class EpisodeFileRenameResult:
    media_id: str
    folder: str
    action: str
    renamed_files: tuple[EpisodeFileRenameOperation, ...]
    skipped_files: tuple[EpisodeFileRenameSkip, ...]
    active_folders: tuple[str, ...]
    binding: ScrapeBinding
