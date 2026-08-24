from __future__ import annotations

import os
import re
from contextlib import suppress
from pathlib import Path

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

    async def get_or_cache(
        self,
        media_id: str,
        category: str,
        external_id: str,
        remote_url: str | None,
    ) -> Path:
        item = self._catalog.get_media(media_id)
        if item is None:
            raise MediaNotFoundError(media_id)
        if category not in self.categories or not self._safe_id.fullmatch(external_id):
            raise ProviderArtworkUnavailableError("INVALID_PROVIDER_ARTWORK_PATH")

        directory = item.root_path / ".cymediaflow" / "artwork" / category
        cached = self._find(directory, external_id)
        if cached is not None:
            return cached
        if not remote_url:
            raise ProviderArtworkUnavailableError()

        image = await self._downloader.download(remote_url)
        if image.warning_code or not image.content or not image.extension:
            raise ProviderArtworkUnavailableError(
                image.warning_code or "PROVIDER_ARTWORK_NOT_FOUND"
            )

        directory.mkdir(parents=True, exist_ok=True)
        self._ensure_ignore_marker(item.root_path)
        target = directory / f"{external_id}{image.extension}"
        try:
            with target.open("xb") as handle:
                handle.write(image.content)
                handle.flush()
                os.fsync(handle.fileno())
        except FileExistsError:
            cached = self._find(directory, external_id)
            if cached is not None:
                return cached
            raise ProviderArtworkUnavailableError("PROVIDER_ARTWORK_WRITE_FAILED") from None
        except OSError as exc:
            with suppress(OSError):
                target.unlink()
            raise ProviderArtworkUnavailableError("PROVIDER_ARTWORK_WRITE_FAILED") from exc
        return target

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
