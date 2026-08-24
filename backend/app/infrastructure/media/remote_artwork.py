from __future__ import annotations

from urllib.parse import urlparse

import httpx

from app.domain.artwork import RemoteArtwork


class HttpRemoteArtworkDownloader:
    _allowed_hosts = frozenset({"lain.bgm.tv", "image.tmdb.org"})
    _maximum_bytes = 20 * 1024 * 1024
    _media_extensions = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
    }

    def __init__(
        self,
        user_agent: str,
        timeout_seconds: float,
        proxies: dict[str, str | None] | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._user_agent = user_agent
        self._timeout_seconds = timeout_seconds
        self._proxies = proxies or {}
        self._transport = transport

    async def download(self, url: str) -> RemoteArtwork:
        parsed = urlparse(url)
        host = (parsed.hostname or "").casefold()
        if not self._allowed_url(parsed):
            return RemoteArtwork(warning_code="REMOTE_ARTWORK_URL_REJECTED")

        options: dict[str, object] = {}
        proxy = self._proxies.get(host)
        if self._transport is None and proxy:
            options["proxy"] = proxy
        try:
            async with httpx.AsyncClient(
                headers={"User-Agent": self._user_agent, "Accept": "image/*"},
                timeout=self._timeout_seconds,
                follow_redirects=True,
                transport=self._transport,
                **options,
            ) as client:
                response = await client.get(url)
                response.raise_for_status()
        except httpx.HTTPError:
            return RemoteArtwork(warning_code="REMOTE_ARTWORK_DOWNLOAD_FAILED")

        if not self._allowed_url(urlparse(str(response.url))):
            return RemoteArtwork(warning_code="REMOTE_ARTWORK_URL_REJECTED")
        content = response.content
        media_type = response.headers.get("content-type", "").split(";", 1)[0].casefold()
        extension = self._media_extensions.get(media_type)
        if (
            extension is None
            or not content
            or len(content) > self._maximum_bytes
            or not self._valid_signature(content, extension)
        ):
            return RemoteArtwork(warning_code="REMOTE_ARTWORK_INVALID")
        return RemoteArtwork(content=content, extension=extension)

    @staticmethod
    def _valid_signature(content: bytes, extension: str) -> bool:
        if extension == ".jpg":
            return content.startswith(b"\xff\xd8\xff")
        if extension == ".png":
            return content.startswith(b"\x89PNG\r\n\x1a\n")
        if extension == ".webp":
            return len(content) >= 12 and content.startswith(b"RIFF") and content[8:12] == b"WEBP"
        return False

    @classmethod
    def _allowed_url(cls, parsed) -> bool:
        host = (parsed.hostname or "").casefold()
        if parsed.scheme != "https" or host not in cls._allowed_hosts:
            return False
        return (host == "lain.bgm.tv" and parsed.path.startswith("/pic/")) or (
            host == "image.tmdb.org" and parsed.path.startswith("/t/p/")
        )
