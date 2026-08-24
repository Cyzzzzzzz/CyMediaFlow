from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MediaStreamInfo:
    stream_type: str
    codec: str | None = None
    profile: str | None = None
    bit_rate: int | None = None
    width: int | None = None
    height: int | None = None
    display_aspect_ratio: str | None = None
    frame_rate: float | None = None
    field_order: str | None = None
    pixel_format: str | None = None
    bit_depth: int | None = None
    channels: int | None = None
    channel_layout: str | None = None
    sample_rate: int | None = None
    language: str | None = None
    title: str | None = None
    default: bool = False
    forced: bool = False
    duration_seconds: float | None = None


@dataclass(frozen=True, slots=True)
class MediaFileInfo:
    format_name: str | None
    duration_seconds: float | None
    bit_rate: int | None
    size: int | None
    streams: tuple[MediaStreamInfo, ...]


@dataclass(frozen=True, slots=True)
class MediaProbeResult:
    media: MediaFileInfo | None
    warning_code: str | None = None
