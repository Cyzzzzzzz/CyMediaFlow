from __future__ import annotations

import asyncio
import json
import os
import subprocess
from pathlib import Path

from app.domain.media_probe import MediaFileInfo, MediaProbeResult, MediaStreamInfo


class FfprobeMediaProbe:
    def __init__(self, executable: str = "ffprobe", timeout_seconds: float = 30.0) -> None:
        self._executable = executable
        self._timeout_seconds = max(1.0, timeout_seconds)

    async def probe(self, path: Path) -> MediaProbeResult:
        if not path.is_file():
            return MediaProbeResult(None, "FFPROBE_MEDIA_NOT_FOUND")
        creation_flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        try:
            process = await asyncio.create_subprocess_exec(
                self._executable,
                "-v",
                "error",
                "-print_format",
                "json",
                "-show_format",
                "-show_streams",
                str(path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                creationflags=creation_flags,
            )
        except FileNotFoundError:
            return MediaProbeResult(None, "FFPROBE_UNAVAILABLE")
        except OSError:
            return MediaProbeResult(None, "FFPROBE_START_FAILED")

        try:
            stdout, _ = await asyncio.wait_for(process.communicate(), timeout=self._timeout_seconds)
        except TimeoutError:
            process.kill()
            await process.wait()
            return MediaProbeResult(None, "FFPROBE_TIMEOUT")
        if process.returncode != 0:
            return MediaProbeResult(None, "FFPROBE_FAILED")
        try:
            payload = json.loads(stdout.decode("utf-8", errors="replace"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return MediaProbeResult(None, "FFPROBE_INVALID_OUTPUT")
        if not isinstance(payload, dict):
            return MediaProbeResult(None, "FFPROBE_INVALID_OUTPUT")
        return MediaProbeResult(self._map_media(payload))

    @classmethod
    def _map_media(cls, payload: dict[str, object]) -> MediaFileInfo:
        raw_format = payload.get("format")
        media_format = raw_format if isinstance(raw_format, dict) else {}
        raw_streams = payload.get("streams")
        streams = raw_streams if isinstance(raw_streams, list) else []
        return MediaFileInfo(
            format_name=_text(media_format.get("format_name")),
            duration_seconds=_float(media_format.get("duration")),
            bit_rate=_int(media_format.get("bit_rate")),
            size=_int(media_format.get("size")),
            streams=tuple(
                cls._map_stream(stream) for stream in streams if isinstance(stream, dict)
            ),
        )

    @staticmethod
    def _map_stream(stream: dict[str, object]) -> MediaStreamInfo:
        raw_tags = stream.get("tags")
        tags = raw_tags if isinstance(raw_tags, dict) else {}
        raw_disposition = stream.get("disposition")
        disposition = raw_disposition if isinstance(raw_disposition, dict) else {}
        return MediaStreamInfo(
            stream_type=_text(stream.get("codec_type")) or "unknown",
            codec=_text(stream.get("codec_name")),
            profile=_text(stream.get("profile")),
            bit_rate=_int(stream.get("bit_rate")),
            width=_int(stream.get("width")),
            height=_int(stream.get("height")),
            display_aspect_ratio=_text(stream.get("display_aspect_ratio")),
            frame_rate=_ratio(stream.get("avg_frame_rate")) or _ratio(stream.get("r_frame_rate")),
            field_order=_text(stream.get("field_order")),
            pixel_format=_text(stream.get("pix_fmt")),
            bit_depth=_int(stream.get("bits_per_raw_sample"))
            or _int(stream.get("bits_per_sample")),
            channels=_int(stream.get("channels")),
            channel_layout=_text(stream.get("channel_layout")),
            sample_rate=_int(stream.get("sample_rate")),
            language=_text(tags.get("language")),
            title=_text(tags.get("title")),
            default=bool(_int(disposition.get("default")) or 0),
            forced=bool(_int(disposition.get("forced")) or 0),
            duration_seconds=_float(stream.get("duration")),
        )


def _text(value: object) -> str | None:
    return str(value).strip() if value is not None and str(value).strip() else None


def _int(value: object) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _float(value: object) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _ratio(value: object) -> float | None:
    text = _text(value)
    if not text or text in {"0/0", "N/A"}:
        return None
    if "/" not in text:
        return _float(text)
    numerator, denominator = text.split("/", 1)
    top = _float(numerator)
    bottom = _float(denominator)
    return top / bottom if top is not None and bottom else None
