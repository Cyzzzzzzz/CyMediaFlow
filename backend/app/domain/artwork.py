from __future__ import annotations

from dataclasses import dataclass

IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp")


@dataclass(frozen=True, slots=True)
class ArtworkGenerationResult:
    created: bool
    warning_code: str | None = None


@dataclass(frozen=True, slots=True)
class RemoteArtwork:
    content: bytes | None = None
    extension: str | None = None
    warning_code: str | None = None


@dataclass(frozen=True, slots=True)
class ArtworkExtractionIssue:
    relative_path: str
    reason: str


@dataclass(frozen=True, slots=True)
class SeasonArtworkExtractionResult:
    media_id: str
    season_number: int
    target_count: int
    created_files: tuple[str, ...]
    skipped_files: tuple[ArtworkExtractionIssue, ...]
    failed_files: tuple[ArtworkExtractionIssue, ...]
