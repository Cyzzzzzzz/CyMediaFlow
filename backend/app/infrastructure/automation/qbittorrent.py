from __future__ import annotations

from urllib.parse import urlparse

import httpx


class QbittorrentError(Exception):
    pass


class QbittorrentClient:
    """Small qB Web API adapter. Every operation authenticates before using its session."""

    def __init__(self, base_url: str, username: str, password: str) -> None:
        parsed = urlparse(base_url)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
        ):
            raise ValueError("qBittorrent 地址必须是 HTTP 或 HTTPS URL")
        self._base_url = base_url.rstrip("/") + "/api/v2/"
        self._username = username
        self._password = password

    async def _session(self) -> httpx.AsyncClient:
        client = httpx.AsyncClient(base_url=self._base_url, timeout=20.0, trust_env=False)
        try:
            response = await client.post(
                "auth/login",
                data={
                    "username": self._username,
                    "password": self._password,
                },
            )
            if response.status_code != 200 or response.text.strip() != "Ok.":
                raise QbittorrentError("qBittorrent 登录失败")
            return client
        except Exception:
            await client.aclose()
            raise

    async def test_connection(self) -> str:
        client = await self._session()
        try:
            response = await client.get("app/version")
            response.raise_for_status()
            return response.text.strip()
        finally:
            await client.aclose()

    async def add(self, url: str, save_path: str, tag: str) -> bool:
        client = await self._session()
        try:
            response = await client.post(
                "torrents/add",
                data={
                    "urls": url,
                    "savepath": save_path,
                    "tags": tag,
                    "autoTMM": "false",
                    "contentLayout": "NoSubfolder",
                },
            )
            if response.status_code not in {200, 202}:
                raise QbittorrentError(f"qBittorrent 拒绝任务（HTTP {response.status_code}）")
            if response.text.strip() == "Ok.":
                return True
            try:
                result = response.json()
            except ValueError as exc:
                raise QbittorrentError("qBittorrent 返回未知添加结果") from exc
            if isinstance(result, dict) and (
                result.get("success_count", 0) or result.get("pending_count", 0)
            ):
                return True
            raise QbittorrentError("qBittorrent 未接受任务；可能是重复或资源无效")
        finally:
            await client.aclose()

    async def by_tag(self, tag: str) -> list[dict]:
        client = await self._session()
        try:
            response = await client.get("torrents/info", params={"tag": tag})
            response.raise_for_status()
            result = response.json()
            return result if isinstance(result, list) else []
        finally:
            await client.aclose()

    async def files(self, torrent_hash: str) -> list[dict]:
        client = await self._session()
        try:
            response = await client.get("torrents/files", params={"hash": torrent_hash})
            response.raise_for_status()
            result = response.json()
            return result if isinstance(result, list) else []
        finally:
            await client.aclose()

    async def rename_file(self, torrent_hash: str, old_path: str, new_path: str) -> None:
        client = await self._session()
        try:
            response = await client.post(
                "torrents/renameFile",
                data={
                    "hash": torrent_hash,
                    "oldPath": old_path,
                    "newPath": new_path,
                },
            )
            if response.status_code >= 300:
                raise QbittorrentError(f"qBittorrent 文件重命名失败（HTTP {response.status_code}）")
        finally:
            await client.aclose()
