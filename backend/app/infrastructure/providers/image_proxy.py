from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import httpx

from app.core.errors import InvalidProviderImageError, ProviderUnavailableError


@dataclass(frozen=True, slots=True)
class CachedImage:
    content: bytes
    media_type: str


class BangumiImageProxy:
    _allowed_hosts = frozenset({"lain.bgm.tv"})
    _maximum_bytes = 8 * 1024 * 1024

    def __init__(
        self,
        cache_dir: Path,
        user_agent: str,
        timeout_seconds: float,
        proxy_url: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._cache_dir = cache_dir
        self._user_agent = user_agent
        self._timeout_seconds = timeout_seconds
        self._proxy_url = proxy_url
        self._transport = transport

    @property
    def proxy_url(self) -> str | None:
        return self._proxy_url

    def set_proxy_url(self, proxy_url: str | None) -> None:
        self._proxy_url = proxy_url

    async def get(self, url: str) -> CachedImage:
        self._validate_url(url)
        cache_path = self._cache_dir / hashlib.sha256(url.encode()).hexdigest()
        type_path = cache_path.with_suffix(".type")
        if cache_path.is_file() and type_path.is_file():
            return CachedImage(
                content=cache_path.read_bytes(),
                media_type=type_path.read_text(encoding="ascii"),
            )

        try:
            client_options: dict[str, object] = {}
            if self._transport is None and self._proxy_url:
                client_options["proxy"] = self._proxy_url
            async with httpx.AsyncClient(
                headers={"User-Agent": self._user_agent, "Accept": "image/*"},
                timeout=self._timeout_seconds,
                follow_redirects=True,
                transport=self._transport,
                **client_options,
            ) as client:
                response = await client.get(url)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ProviderUnavailableError("Bangumi 图片暂时无法加载") from exc

        media_type = response.headers.get("content-type", "").split(";", 1)[0]
        if not media_type.startswith("image/") or len(response.content) > self._maximum_bytes:
            raise ProviderUnavailableError("Bangumi 图片响应无效")

        self._cache_dir.mkdir(parents=True, exist_ok=True)
        cache_path.write_bytes(response.content)
        type_path.write_text(media_type, encoding="ascii")
        return CachedImage(content=response.content, media_type=media_type)

    @classmethod
    def _validate_url(cls, url: str) -> None:
        parsed = urlparse(url)
        if (
            parsed.scheme != "https"
            or parsed.hostname not in cls._allowed_hosts
            or not parsed.path.startswith("/pic/")
        ):
            raise InvalidProviderImageError
