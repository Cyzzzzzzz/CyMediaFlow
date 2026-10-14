from __future__ import annotations

import base64
import hashlib
from pathlib import PurePosixPath
from uuid import uuid4

import httpx

from app.infrastructure.automation.feature_config import http_url
from app.infrastructure.automation.torrent_source import fetch_torrent


class Aria2Client:
    def __init__(
        self, url: str, secret: str = "", proxy: str | None = None, stored_gid: str | None = None
    ):
        self.url, self.secret, self.proxy = http_url(url), secret, proxy
        self.stored_gid = stored_gid

    async def rpc(self, method: str, *params):
        args = (["token:" + self.secret] if self.secret else []) + list(params)
        async with httpx.AsyncClient(timeout=20, trust_env=False) as client:
            response = await client.post(
                self.url,
                json={
                    "jsonrpc": "2.0",
                    "id": uuid4().hex,
                    "method": "aria2." + method,
                    "params": args,
                },
            )
            response.raise_for_status()
            result = response.json()
            if result.get("error"):
                raise ValueError("aria2 请求失败，请检查 RPC 配置和任务状态")
            return result["result"]

    async def test_connection(self) -> str:
        return "aria2 " + (await self.rpc("getVersion"))["version"]

    @staticmethod
    def gid(tag: str) -> str:
        return hashlib.sha256(("cymediaflow:" + tag).encode()).hexdigest()[:16]

    async def add(self, url: str, save_path: str, tag: str) -> bool:
        options = {
            "dir": save_path,
            "gid": self.gid(tag),
            "auto-file-renaming": "false",
            "allow-overwrite": "false",
            "seed-time": "0",
        }
        if url.startswith("magnet:"):
            await self.rpc("addUri", [url], options)
        else:
            content = await fetch_torrent(url, self.proxy)
            await self.rpc("addTorrent", base64.b64encode(content).decode(), [], options)
        return True

    async def by_tag(self, tag: str) -> list[dict]:
        # tellStatus error 1 can also mean auth error; never interpret all RPC errors as absent.
        tasks = await self.rpc("tellActive")
        for method in ("tellWaiting", "tellStopped"):
            for offset in range(0, 100000, 1000):
                page = await self.rpc(method, offset, 1000)
                tasks += page
                if len(page) < 1000:
                    break
            else:
                raise ValueError("aria2 任务过多，请清理历史记录后重新同步")
        lookup = {t["gid"]: t for t in tasks}
        parent = self.stored_gid or self.gid(tag)
        task = lookup.get(parent) or lookup.get(self.gid(tag))
        if not task:
            task = next((t for t in tasks if t.get("following") == parent), None)
        for _ in range(4):
            if task and task.get("followedBy"):
                task = lookup.get(task["followedBy"][0]) or await self.rpc(
                    "tellStatus", task["followedBy"][0]
                )
            else:
                break
        if not task:
            return []
        total = max(1, int(task.get("totalLength", 0)))
        return [
            {
                "hash": task["gid"],
                "parent_hash": parent if task["gid"] != parent else None,
                "progress": int(task.get("completedLength", 0)) / total,
                "state": task["status"],
                "save_path": task.get("dir", ""),
                "error": task.get("errorMessage"),
            }
        ]

    async def files(self, gid: str) -> list[dict]:
        task = await self.rpc("tellStatus", gid)
        root = PurePosixPath(task["dir"])
        return [
            {"name": PurePosixPath(f["path"]).relative_to(root).as_posix()}
            for f in task["files"]
            if f.get("selected", "true") == "true"
        ]

    async def action(self, gid: str, action: str) -> None:
        if action == "remove":
            status = await self.rpc("tellStatus", gid)
            if status["status"] in {"complete", "error", "removed"}:
                await self.rpc("removeDownloadResult", gid)
                return
        method = {"pause": "pause", "resume": "unpause", "remove": "remove"}.get(action)
        if not method:
            raise ValueError("aria2 不支持此操作")
        await self.rpc(method, gid)
