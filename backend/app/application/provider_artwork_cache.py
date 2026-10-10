from __future__ import annotations

import asyncio
import os
import re
from contextlib import suppress
from pathlib import Path
from tempfile import NamedTemporaryFile

from starlette.concurrency import run_in_threadpool

from app.application.ports import MediaCatalogPort, RemoteArtworkDownloaderPort
from app.core.errors import MediaNotFoundError, ProviderArtworkUnavailableError
from app.domain.artwork import IMAGE_EXTENSIONS


class ProviderArtworkCache:
    categories = frozenset({"persons", "characters", "voice-actors", "related"})
    _safe_id = re.compile(r"^[A-Za-z0-9_-]{1,100}$")

    def __init__(
        self,
        catalog: MediaCatalogPort,
        downloader: RemoteArtworkDownloaderPort,
    ) -> None:
        self._catalog = catalog
        self._downloader = downloader
        self._locks = tuple(asyncio.Lock() for _ in range(32))
        self._downloads = asyncio.Semaphore(4)

    async def get_or_cache(
        self,
        media_id: str,
        category: str,
        external_id: str,
        remote_url: str | None,
    ) -> Path:
        if category not in self.categories or not self._safe_id.fullmatch(external_id):
            raise ProviderArtworkUnavailableError("INVALID_PROVIDER_ARTWORK_PATH")
        root = await run_in_threadpool(self._catalog.get_media_root, media_id)
        if root is None:
            raise MediaNotFoundError(media_id)
        directory = root / ".cymediaflow" / "artwork" / category
        cached = await run_in_threadpool(self._find, directory, external_id)
        if cached is not None:
            return cached
        if not remote_url:
            raise ProviderArtworkUnavailableError()

        lock = self._locks[hash((media_id, category, external_id)) % len(self._locks)]
        async with lock:
            cached = await run_in_threadpool(self._find, directory, external_id)
            if cached is not None:
                return cached
            async with self._downloads:
                image = await self._downloader.download(remote_url)
            if image.warning_code or not image.content or not image.extension:
                raise ProviderArtworkUnavailableError(
                    image.warning_code or "PROVIDER_ARTWORK_NOT_FOUND"
                )
            return await run_in_threadpool(
                self._save, root, directory, external_id, image.content, image.extension
            )

    def _save(
        self, root: Path, directory: Path, external_id: str, content: bytes, extension: str
    ) -> Path:
        temporary: Path | None = None
        try:
            directory.mkdir(parents=True, exist_ok=True)
            self._ensure_ignore_marker(root)
            target = directory / f"{external_id}{extension}"
            with NamedTemporaryFile(dir=directory, suffix=".tmp", delete=False) as handle:
                temporary = Path(handle.name)
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            cached = self._find(directory, external_id)
            if cached is not None:
                return cached
            temporary.replace(target)
            return target
        except OSError as exc:
            raise ProviderArtworkUnavailableError("PROVIDER_ARTWORK_WRITE_FAILED") from exc
        finally:
            if temporary is not None:
                with suppress(OSError):
                    temporary.unlink(missing_ok=True)

    @staticmethod
    def _find(directory: Path, stem: str) -> Path | None:
        return next(
            (
                directory / f"{stem}{extension}"
                for extension in IMAGE_EXTENSIONS
                if (directory / f"{stem}{extension}").is_file()
            ),
            None,
        )

    @staticmethod
    def _ensure_ignore_marker(root: Path) -> None:
        marker = root / ".cymediaflow" / ".ignore"
        try:
            with marker.open("xb"):
                pass
        except FileExistsError:
            pass
