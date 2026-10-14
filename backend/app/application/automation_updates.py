from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
from contextlib import suppress
from datetime import datetime, timezone

import httpx

from app.core.errors import DomainError


class AutomationUpdates:
    def __init__(self, automation, documents, config, bangumi):
        self.automation, self.documents, self.config = automation, documents, config
        self.bangumi = bangumi
        self._lock = asyncio.Lock()

    def calendar(self) -> dict:
        cached = self.documents.get("automation:calendar", {"subjects": {}, "updated_at": None})
        rows = []
        for rule in self.automation.list_subscriptions():
            if rule["archived"]:
                continue
            remote = (
                cached["subjects"].get(rule["provider_id"], {})
                if rule["provider"] == "bangumi"
                else {}
            )
            rows.append(
                {
                    **rule,
                    "air_weekday": rule["air_weekday"]
                    if rule["air_weekday"] is not None
                    else remote.get("weekday"),
                    "air_date": remote.get("air_date"),
                }
            )
        return {"items": rows, "updated_at": cached["updated_at"]}

    async def refresh_calendar(self) -> dict:
        try:
            async with self.bangumi._client() as client:
                response = await client.get("/calendar")
                response.raise_for_status()
                payload = response.json()
            subjects = {}
            for day in payload:
                weekday = int(day["weekday"]["id"]) - 1
                for item in day.get("items", []):
                    subjects[str(item["id"])] = {
                        "weekday": weekday,
                        "air_date": item.get("air_date"),
                    }
            self.documents.put(
                "automation:calendar",
                {"subjects": subjects, "updated_at": datetime.now(timezone.utc).isoformat()},
            )
            return self.calendar()
        except Exception as exc:
            raise DomainError("CALENDAR_FAILED", "Bangumi 日历更新失败，保留上次结果", 503) from exc

    def notifications(self, user_id: str = "local") -> dict:
        state = self.documents.get("automation:inbox:" + user_id, {"read_to": 0})
        items = [
            {
                "id": e.id,
                "kind": e.kind,
                "message": e.message,
                "created_at": e.created_at,
                "read": e.id <= state["read_to"],
            }
            for e in self.automation._repo.list_events(100)
            if e.kind not in {"rss_refresh", "download_progress"}
        ]
        return {"items": items, "unread": sum(not e["read"] for e in items)}

    def mark_read(self, through: int, user_id: str = "local"):
        previous = self.documents.get("automation:inbox:" + user_id, {"read_to": 0})
        last = self.automation._repo.list_events(1)
        maximum = last[0].id if last else 0
        self.documents.put(
            "automation:inbox:" + user_id,
            {"read_to": max(previous["read_to"], min(through, maximum))},
        )

    async def webhook(self, payload: dict):
        config = self.config.private()
        if not config.get("webhook_url"):
            raise DomainError("WEBHOOK_NOT_CONFIGURED", "请先保存 Webhook 地址")
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
        headers = {"Content-Type": "application/json", "X-CyMediaFlow-Event": str(payload["id"])}
        if config.get("webhook_secret"):
            signature = hmac.new(
                config["webhook_secret"].encode(), body, hashlib.sha256
            ).hexdigest()
            headers["X-CyMediaFlow-Signature"] = "sha256=" + signature
        try:
            async with httpx.AsyncClient(timeout=10, trust_env=False) as client:
                response = await client.post(config["webhook_url"], content=body, headers=headers)
                response.raise_for_status()
        except Exception as exc:
            raise DomainError("WEBHOOK_FAILED", "通知发送失败，请检查地址和接收端", 503) from exc

    def version(self) -> dict:
        return {
            "current": os.environ.get("CYMEDIAFLOW_BUILD_REVISION", "development"),
            **self.documents.get("automation:version", {"checked_at": None, "latest": None}),
        }

    async def check_version(self) -> dict:
        proxy = self.automation.get_config().rss_proxy_url or None
        try:
            async with httpx.AsyncClient(timeout=15, proxy=proxy, trust_env=False) as client:
                response = await client.get(
                    "https://api.github.com/repos/Cyzzzzzzz/CyMediaFlow/commits/main",
                    headers={"Accept": "application/vnd.github+json", "User-Agent": "CyMediaFlow"},
                )
                response.raise_for_status()
                data = response.json()
            previous = self.documents.get("automation:version", {})
            self.documents.put(
                "automation:version",
                {
                    "latest": data["sha"],
                    "url": "https://github.com/Cyzzzzzzz/CyMediaFlow/commits/main",
                    "checked_at": datetime.now(timezone.utc).isoformat(),
                },
            )
            current = os.environ.get("CYMEDIAFLOW_BUILD_REVISION", "development")
            if (
                current != "development"
                and current != data["sha"]
                and previous.get("latest") != data["sha"]
            ):
                self.automation._repo.add_event(
                    "version_available", "GitHub main 有新版本，可通过 NAS 更新脚本升级"
                )
            return self.version()
        except Exception as exc:
            raise DomainError(
                "VERSION_CHECK_FAILED", "GitHub 版本检查失败，保留上次结果", 503
            ) from exc

    async def tick(self):
        if self._lock.locked():
            return
        async with self._lock:
            config = self.config.private()
            now = datetime.now(timezone.utc)
            if config.get("calendar_auto_refresh"):
                previous = self.documents.get("automation:calendar:attempt", {})
                if previous.get("day") != now.date().isoformat():
                    self.documents.put(
                        "automation:calendar:attempt", {"day": now.date().isoformat()}
                    )
                    with suppress(DomainError):
                        await self.refresh_calendar()
            if config.get("webhook_enabled"):
                cursor = self.documents.get("automation:webhook:cursor")
                if cursor is None:
                    last = self.automation._repo.list_events(1)
                    self.documents.put(
                        "automation:webhook:cursor", {"id": last[0].id if last else 0}
                    )
                else:
                    for event in self.automation._repo.events_after(cursor["id"], 20):
                        if event.kind in config.get("webhook_events", []):
                            receipt_key = f"automation:webhook:receipt:{event.id}"
                            receipt = self.documents.get(receipt_key, {"attempts": 0})
                            if receipt.get("status") != "sent" and receipt["attempts"] < 5:
                                retry_at = (
                                    datetime.fromisoformat(receipt["next_at"])
                                    if receipt.get("next_at")
                                    else now
                                )
                                if retry_at > now:
                                    break
                                try:
                                    await self.webhook(
                                        {
                                            "id": event.id,
                                            "kind": event.kind,
                                            "message": event.message,
                                        }
                                    )
                                except DomainError:
                                    from datetime import timedelta

                                    attempts = receipt["attempts"] + 1
                                    self.documents.put(
                                        receipt_key,
                                        {
                                            "attempts": attempts,
                                            "status": "failed",
                                            "next_at": (
                                                now + timedelta(seconds=min(3600, 30 * 2**attempts))
                                            ).isoformat(),
                                        },
                                    )
                                    break
                                self.documents.put(
                                    receipt_key,
                                    {"attempts": receipt["attempts"] + 1, "status": "sent"},
                                )
                        self.documents.put("automation:webhook:cursor", {"id": event.id})
            if config.get("version_auto_check"):
                previous = self.documents.get("automation:version:attempt", {})
                if previous.get("day") != now.date().isoformat():
                    self.documents.put(
                        "automation:version:attempt", {"day": now.date().isoformat()}
                    )
                    await self.check_version()
