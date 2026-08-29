from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
from contextlib import suppress
from pathlib import Path
from uuid import uuid4

from app.domain.artwork import ArtworkGenerationResult


class FfmpegEpisodeArtworkGenerator:
    def __init__(
        self,
        executable: str = "ffmpeg",
        timeout_seconds: float = 60.0,
        capture_percent: float = 25.0,
    ) -> None:
        self._executable = executable
        self._timeout_seconds = max(1.0, timeout_seconds)
        self._capture_percent = min(90.0, max(5.0, capture_percent))

    async def generate(
        self,
        video_path: Path,
        output_path: Path,
        duration_seconds: float | None = None,
        overwrite_existing: bool = False,
    ) -> ArtworkGenerationResult:
        if output_path.is_file() and not overwrite_existing:
            return ArtworkGenerationResult(False)
        if not video_path.is_file():
            return ArtworkGenerationResult(False, "FFMPEG_MEDIA_NOT_FOUND")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = output_path.with_name(
            f".{output_path.stem}.cymediaflow-{uuid4().hex}{output_path.suffix}"
        )
        creation_flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        try:
            process = await asyncio.create_subprocess_exec(
                self._executable,
                "-hide_banner",
                "-loglevel",
                "error",
                "-ss",
                self._capture_timestamp(duration_seconds),
                "-i",
                str(video_path),
                "-frames:v",
                "1",
                "-vf",
                "scale=960:-2:force_original_aspect_ratio=decrease",
                "-q:v",
                "2",
                "-n",
                str(temporary),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                creationflags=creation_flags,
            )
        except FileNotFoundError:
            return ArtworkGenerationResult(False, "FFMPEG_UNAVAILABLE")
        except OSError:
            return ArtworkGenerationResult(False, "FFMPEG_START_FAILED")

        try:
            await asyncio.wait_for(process.communicate(), timeout=self._timeout_seconds)
        except TimeoutError:
            process.kill()
            await process.wait()
            with suppress(OSError):
                temporary.unlink()
            return ArtworkGenerationResult(False, "FFMPEG_TIMEOUT")
        if process.returncode != 0 or not temporary.is_file() or temporary.stat().st_size == 0:
            with suppress(OSError):
                temporary.unlink()
            return ArtworkGenerationResult(False, "FFMPEG_CAPTURE_FAILED")

        if overwrite_existing:
            try:
                os.replace(temporary, output_path)
            except OSError:
                with suppress(OSError):
                    temporary.unlink()
                return ArtworkGenerationResult(False, "ARTWORK_WRITE_FAILED")
            return ArtworkGenerationResult(True)

        try:
            with output_path.open("xb") as destination, temporary.open("rb") as source:
                shutil.copyfileobj(source, destination)
                destination.flush()
                os.fsync(destination.fileno())
        except FileExistsError:
            return ArtworkGenerationResult(False)
        except OSError:
            with suppress(OSError):
                output_path.unlink()
            return ArtworkGenerationResult(False, "ARTWORK_WRITE_FAILED")
        finally:
            with suppress(OSError):
                temporary.unlink()
        return ArtworkGenerationResult(True)

    def _capture_timestamp(self, duration_seconds: float | None) -> str:
        if duration_seconds is None or duration_seconds <= 0:
            seconds = 60.0
        else:
            seconds = duration_seconds * self._capture_percent / 100.0
            seconds = min(max(30.0, seconds), max(1.0, duration_seconds - 10.0), 600.0)
        return f"{seconds:.3f}"
