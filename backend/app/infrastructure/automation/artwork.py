from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path
from tempfile import NamedTemporaryFile

from app.core.errors import DomainError
from app.domain.automation_subscription import valid_poster_url
from app.infrastructure.media.remote_artwork import HttpRemoteArtworkDownloader


class SubscriptionArtworkCache:
    def __init__(self, directory: Path, downloader: HttpRemoteArtworkDownloader):
        self._directory = directory
        self._downloader = downloader
        self._locks = tuple(asyncio.Lock() for _ in range(32))
        self._semaphore = asyncio.Semaphore(4)

    async def get(self, url: str) -> Path:
        if not url or not valid_poster_url(url):
            raise DomainError("INVALID_POSTER_URL", "海报来源无效")
        digest = hashlib.sha256(url.encode()).hexdigest()
        target = self._directory / digest
        async with self._locks[int(digest[:8], 16) % len(self._locks)]:
            if await asyncio.to_thread(target.is_file):
                return target
            async with self._semaphore:
                result = await self._downloader.download(url)
            if not result.content:
                raise DomainError("POSTER_UNAVAILABLE", "订阅海报暂不可用", 503)
            await asyncio.to_thread(self._publish, target, result.content)
        return target

    @staticmethod
    def _publish(target: Path, content: bytes) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with NamedTemporaryFile(dir=target.parent, delete=False) as handle:
                temporary = Path(handle.name)
                handle.write(content)
            temporary.replace(target)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
