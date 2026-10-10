from __future__ import annotations

import hashlib
from contextlib import suppress
from pathlib import Path
from tempfile import NamedTemporaryFile
from threading import Lock

from fastapi import Request
from fastapi.responses import FileResponse, Response
from PIL import Image, ImageOps, UnidentifiedImageError


class ImageFileService:
    """Serve local artwork with conditional HTTP caching and persistent small previews."""

    def __init__(self, cache_dir: Path) -> None:
        self._cache_dir = cache_dir
        self._locks = tuple(Lock() for _ in range(32))

    def response(self, request: Request, source: Path, width: int | None = None) -> Response:
        if width is not None:
            width = next(size for size in (160, 320, 640) if size >= width)
        stat = source.stat()
        version = f"{source}:{stat.st_mtime_ns}:{stat.st_size}:{width}:webp-v1"
        digest = hashlib.sha256(version.encode("utf-8")).hexdigest()
        headers = {
            # Overwritten artwork must revalidate even at the same URL.
            "Cache-Control": "private, max-age=0, must-revalidate",
            "ETag": f'"{digest}"',
        }
        validators = request.headers.get("if-none-match", "").split(",")
        if any(tag.strip().removeprefix("W/") in {headers["ETag"], "*"} for tag in validators):
            return Response(status_code=304, headers=headers)
        target = self._thumbnail(source, width, digest) if width is not None else source
        return FileResponse(target, headers=headers)

    def _thumbnail(self, source: Path, width: int, digest: str) -> Path:
        target = self._cache_dir / f"{digest}.webp"
        if target.is_file():
            return target
        lock = self._locks[int(digest[:8], 16) % len(self._locks)]
        with lock:
            if target.is_file():
                return target
            temporary: Path | None = None
            try:
                with Image.open(source) as image:
                    image.draft("RGB", (width, width * 2))
                    image = ImageOps.exif_transpose(image)
                    image.thumbnail((width, width * 2), Image.Resampling.LANCZOS)
                    image = image.convert("RGBA" if "A" in image.getbands() else "RGB")
                    self._cache_dir.mkdir(parents=True, exist_ok=True)
                    with NamedTemporaryFile(
                        dir=self._cache_dir, suffix=".tmp", delete=False
                    ) as handle:
                        temporary = Path(handle.name)
                        image.save(handle, format="WEBP", quality=82, method=4)
                    temporary.replace(target)
                return target
            except (OSError, ValueError, UnidentifiedImageError, Image.DecompressionBombError):
                # Keep original artwork available if a preview cannot be produced.
                return source
            finally:
                if temporary is not None:
                    with suppress(OSError):
                        temporary.unlink(missing_ok=True)
