from __future__ import annotations

import asyncio

import httpx

from app.infrastructure.automation.rss import validate_feed_url

MAX_TORRENT_BYTES = 10 * 1024 * 1024


class TorrentSourceError(Exception):
    """Safe to display: never includes a private source URL or its credentials."""


async def fetch_torrent(url: str, proxy_url: str | None) -> bytes:
    try:
        validate_feed_url(url)
        return await asyncio.wait_for(_download(url, proxy_url), timeout=30)
    except TorrentSourceError:
        raise
    except httpx.HTTPStatusError as exc:
        raise TorrentSourceError(
            f"种子文件获取失败（HTTP {exc.response.status_code}）；请检查订阅地址及 RSS 代理"
        ) from exc
    except Exception as exc:
        raise TorrentSourceError("种子文件获取失败；请检查 RSS 代理及来源站点连接") from exc


async def _download(url: str, proxy_url: str | None) -> bytes:
    async with (
        httpx.AsyncClient(
            proxy=proxy_url,
            timeout=20,
            follow_redirects=True,
            trust_env=False,
            headers={"User-Agent": "CyMediaFlow/0.1 RSS"},
        ) as client,
        client.stream("GET", url) as response,
    ):
        response.raise_for_status()
        chunks, size = [], 0
        async for chunk in response.aiter_bytes():
            size += len(chunk)
            if size > MAX_TORRENT_BYTES:
                raise TorrentSourceError("种子文件超过 10 MiB 限制")
            chunks.append(chunk)
        content = b"".join(chunks)
    # Reject common HTML/login responses. qB performs the full metainfo validation.
    if not content.startswith(b"d") or not content.endswith(b"e"):
        raise TorrentSourceError("来源未返回有效种子文件，可能是网页、登录页或失效链接")
    return content
