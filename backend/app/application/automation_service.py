from __future__ import annotations

import asyncio
import json
import logging
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from app.core.errors import DomainError
from app.core.path_safety import path_is_within
from app.domain.automation import (
    analyze_release,
    match_subscription,
    safe_component,
)
from app.domain.automation_subscription import (
    effective_season,
    split_subscription_values,
    subscription_options,
    valid_poster_url,
)
from app.domain.keywords import normalize_keywords
from app.infrastructure.automation.qbittorrent import QbittorrentClient, QbittorrentError
from app.infrastructure.automation.rss import HttpRssClient, validate_feed_url
from app.infrastructure.automation.torrent_source import TorrentSourceError
from app.infrastructure.filesystem.media_scanner import FileSystemMediaCatalog
from app.infrastructure.persistence.automation_repository import AutomationRepository
from app.infrastructure.persistence.settings_repository import SqlAlchemySettingsRepository

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class AutomationConfig:
    enabled: bool = False
    interval_minutes: int = 15
    qb_url: str = ""
    qb_username: str = ""
    qb_password_configured: bool = False
    qb_save_root: str = ""
    rss_proxy_url: str = ""
    default_exclude_keywords: tuple[str, ...] = ()


def public_feed(record: object) -> dict:
    parsed = urlsplit(record.url)
    public_url = urlunsplit((parsed.scheme, parsed.netloc, "/…", "", ""))
    return {
        "id": record.id,
        "name": record.name,
        "url": public_url,
        "enabled": record.enabled,
        "status": record.status,
        "last_checked_at": record.last_checked_at,
        "last_error": record.last_error,
    }


def public_subscription(record: object) -> dict:
    return {
        **subscription_options(record),
        **{
            key: getattr(record, key)
            for key in (
                "id",
                "feed_id",
                "title",
                "folder_name",
                "aliases",
                "season",
                "episode_offset",
                "preferred_group",
                "preferred_resolution",
                "exclude_keywords",
                "enabled",
            )
        },
    }


class AutomationService:
    def __init__(
        self,
        repository: AutomationRepository,
        app_settings: SqlAlchemySettingsRepository,
        media_catalog: FileSystemMediaCatalog,
        media_root: Path,
    ) -> None:
        self._repo = repository
        self._settings = app_settings
        self._catalog = media_catalog
        self._media_root = media_root.resolve(strict=False)
        self._rss = HttpRssClient(app_settings.get("automation_rss_proxy_url") or None)
        self._lock = asyncio.Lock()
        self._task: asyncio.Task[None] | None = None
        self._updates_task: asyncio.Task[None] | None = None
        self.features = None
        self.operations = None
        self.background = None

    def get_config(self) -> AutomationConfig:
        get = self._settings.get
        return AutomationConfig(
            enabled=get("automation_enabled") == "true",
            interval_minutes=int(get("automation_interval_minutes") or "15"),
            qb_url=get("automation_qb_url") or "",
            qb_username=get("automation_qb_username") or "",
            qb_password_configured=bool(get("automation_qb_password")),
            qb_save_root=get("automation_qb_save_root") or "",
            rss_proxy_url=get("automation_rss_proxy_url") or "",
            default_exclude_keywords=tuple(self.default_exclude_keywords()),
        )

    def default_exclude_keywords(self) -> list[str]:
        return normalize_keywords(
            json.loads(self._settings.get("automation_default_exclude_keywords") or "[]")
        )

    def save_config(
        self,
        *,
        enabled: bool,
        interval_minutes: int,
        qb_url: str,
        qb_username: str,
        qb_save_root: str,
        qb_password: str | None,
        rss_proxy_url: str = "",
        clear_qb_password: bool = False,
        default_exclude_keywords: list[str] | None = None,
    ) -> AutomationConfig:
        if not 1 <= interval_minutes <= 1440:
            raise DomainError("INVALID_INTERVAL", "刷新周期须介于 1 与 1440 分钟")
        qb_url = qb_url.strip()
        qb_save_root = qb_save_root.strip().rstrip("/")
        rss_proxy_url = rss_proxy_url.strip()
        if rss_proxy_url:
            try:
                proxy = urlsplit(rss_proxy_url)
            except ValueError as exc:
                raise DomainError("INVALID_RSS_PROXY", "RSS 代理地址无效") from exc
            if (
                proxy.scheme not in {"http", "https"}
                or not proxy.hostname
                or proxy.username
                or proxy.password
            ):
                raise DomainError("INVALID_RSS_PROXY", "RSS 代理须为不含账号密码的 HTTP/HTTPS 地址")
        if qb_url:
            try:
                QbittorrentClient(qb_url, qb_username, qb_password or "")
            except ValueError as exc:
                raise DomainError("INVALID_DOWNLOADER_URL", str(exc)) from exc
        if qb_save_root and (not qb_save_root.startswith("/") or ".." in qb_save_root.split("/")):
            raise DomainError("INVALID_DOWNLOAD_ROOT", "下载器保存目录须为绝对 POSIX 路径")
        stored_password = self._settings.get("automation_qb_password")
        effective_password = (
            ""
            if clear_qb_password
            else (qb_password if qb_password is not None else stored_password)
        )
        aria_configured = (
            self.features
            and self.features.private().get("aria2_url")
            and self.features.private().get("aria2_save_root")
        )
        if (
            enabled
            and not aria_configured
            and (not qb_url or not qb_save_root or not qb_username or not effective_password)
        ):
            raise DomainError(
                "DOWNLOADER_NOT_CONFIGURED", "启用前请填写 qBittorrent 连接和保存目录"
            )
        previous_rss_proxy = self._settings.get("automation_rss_proxy_url") or ""
        values = {
            "automation_enabled": str(enabled).lower(),
            "automation_interval_minutes": str(interval_minutes),
            "automation_qb_url": qb_url,
            "automation_qb_username": qb_username.strip(),
            "automation_qb_save_root": qb_save_root,
            "automation_rss_proxy_url": rss_proxy_url,
        }
        if default_exclude_keywords is not None:
            values["automation_default_exclude_keywords"] = json.dumps(
                normalize_keywords(default_exclude_keywords),
                ensure_ascii=False,
            )
        for key, value in values.items():
            self._settings.set(key, value)
        if qb_password is not None or clear_qb_password:
            self._settings.set(
                "automation_qb_password", "" if clear_qb_password else qb_password or ""
            )
        if rss_proxy_url != previous_rss_proxy:
            self._rss = HttpRssClient(rss_proxy_url or None)
        return self.get_config()

    def _qb(self) -> QbittorrentClient:
        config = self.get_config()
        password = self._settings.get("automation_qb_password") or ""
        if not config.qb_url or not config.qb_username or not password:
            raise DomainError("DOWNLOADER_NOT_CONFIGURED", "请先在自动追番设置里配置 qBittorrent")
        return QbittorrentClient(
            config.qb_url, config.qb_username, password, config.rss_proxy_url or None
        )

    async def test_downloader(self) -> str:
        try:
            return await self._qb().test_connection()
        except DomainError:
            raise
        except Exception as exc:
            raise DomainError("DOWNLOADER_UNAVAILABLE", "qBittorrent 连接测试失败", 503) from exc

    def downloader(self, job=None, kind: str | None = None):
        backend = kind or ((job.naming_json or {}).get("downloader") if job else None)
        if backend == "aria2":
            from app.infrastructure.automation.aria2 import Aria2Client

            config = self.features.private() if self.features else {}
            if not config.get("aria2_url"):
                raise DomainError("ARIA2_NOT_CONFIGURED", "请先在设置里配置 aria2")
            return Aria2Client(
                config["aria2_url"],
                config.get("aria2_secret", ""),
                self.get_config().rss_proxy_url or None,
                stored_gid=job.torrent_hash if job else None,
            )
        return self._qb()

    def save_feed(self, feed_id: int | None, *, name: str, url: str | None, enabled: bool) -> dict:
        current = self._repo.get_feed(feed_id) if feed_id is not None else None
        if feed_id is not None and (current is None or current.deleted):
            raise DomainError("FEED_NOT_FOUND", "RSS 订阅不存在", 404)
        try:
            target_url = validate_feed_url(url) if url else current.url if current else None
        except ValueError as exc:
            raise DomainError("INVALID_FEED_URL", str(exc)) from exc
        if not target_url or not name.strip():
            raise DomainError("INVALID_FEED", "请填写 RSS 名称和地址")
        if any(feed.url == target_url and feed.id != feed_id for feed in self._repo.list_feeds()):
            raise DomainError("DUPLICATE_FEED", "该 RSS 地址已经添加")
        record = self._repo.save_feed(
            feed_id,
            {
                "name": name.strip(),
                "url": target_url,
                "enabled": enabled,
            },
        )
        return public_feed(record)

    def delete_feed(self, feed_id: int) -> None:
        if self._repo.get_feed(feed_id) is None:
            raise DomainError("FEED_NOT_FOUND", "RSS 订阅不存在", 404)
        self._repo.soft_delete_feed(feed_id)

    def save_subscription(self, subscription_id: int | None, values: dict) -> dict:
        feed = self._repo.get_feed(values["feed_id"])
        if feed is None or feed.deleted:
            raise DomainError("FEED_NOT_FOUND", "请先选择有效的 RSS 订阅", 404)
        existing = self._repo.get_subscription(subscription_id) if subscription_id else None
        if subscription_id and (existing is None or existing.deleted):
            raise DomainError("SUBSCRIPTION_NOT_FOUND", "追番规则不存在", 404)
        values = self.prepare_subscription(values)
        return public_subscription(self._repo.save_subscription(subscription_id, values))

    @staticmethod
    def prepare_subscription(values: dict) -> dict:
        values = dict(values)
        try:
            safe_component(values["title"])
            values["title"] = values["title"].strip()
            values["folder_name"] = safe_component(values["folder_name"] or values["title"])
        except ValueError as exc:
            raise DomainError("INVALID_SUBSCRIPTION_PATH", str(exc)) from exc
        values["aliases"] = [alias.strip() for alias in values["aliases"] if alias.strip()]
        values["exclude_keywords"] = normalize_keywords(values["exclude_keywords"])
        if values["season"] < 0 or values["season"] > 99 or abs(values["episode_offset"]) > 999:
            raise DomainError("INVALID_EPISODE_MAPPING", "季号或集数偏移超出允许范围")
        if not 0 <= values["season"] + values.get("season_offset", 0) <= 99:
            raise DomainError("INVALID_EPISODE_MAPPING", "季度偏移后的季号须介于 0 与 99")
        if not valid_poster_url(values.get("poster_url")):
            raise DomainError("INVALID_POSTER_URL", "请使用 Bangumi 或 TMDB 的海报地址")
        source_title = values.get("source_title", "").strip()
        if source_title and source_title not in values["aliases"]:
            values["aliases"].append(source_title)
        return split_subscription_values(values)

    def list_subscriptions(self) -> list[dict]:
        result = []
        for record in self._repo.list_subscriptions():
            item = public_subscription(record)
            item["local_poster_url"] = (
                f"/api/v1/automation/subscriptions/{record.id}/poster"
                if self.local_subscription_poster(record.id)
                else None
            )
            result.append(item)
        return result

    def local_subscription_poster(self, subscription_id: int) -> Path | None:
        record = self._repo.get_subscription(subscription_id)
        if record is None or record.deleted:
            return None
        folder = (self._media_root / record.folder_name).resolve(strict=False)
        if not path_is_within(folder, self._media_root):
            return None
        for name in ("poster.jpg", "poster.png", "poster.webp", "folder.jpg"):
            path = (folder / name).resolve(strict=False)
            if path_is_within(path, self._media_root) and path.is_file():
                return path
        return None

    def delete_subscription(self, subscription_id: int) -> None:
        if self._repo.get_subscription(subscription_id) is None:
            raise DomainError("SUBSCRIPTION_NOT_FOUND", "追番规则不存在", 404)
        self._repo.soft_delete_subscription(subscription_id)

    async def preview_feed(self, feed_id: int) -> list[dict]:
        feed = self._repo.get_feed(feed_id)
        if feed is None or feed.deleted:
            raise DomainError("FEED_NOT_FOUND", "RSS 订阅不存在", 404)
        try:
            entries = await self._rss.fetch(feed.url)
        except Exception as exc:
            self._repo.update_feed_status(feed_id, "error", "连接或 XML 解析失败")
            raise DomainError("RSS_UNAVAILABLE", "RSS 连接或 XML 解析失败", 503) from exc
        self._repo.update_feed_status(feed_id, "connected", None)
        return [
            {"title": entry.title, "analysis": analyze_release(entry.title).json()}
            for entry in entries[:100]
        ]

    async def refresh_feed(self, feed_id: int) -> dict:
        feed = self._repo.get_feed(feed_id)
        if feed is None or feed.deleted:
            raise DomainError("FEED_NOT_FOUND", "RSS 订阅不存在", 404)
        async with self._lock:
            return await self._refresh_feed(feed)

    async def _refresh_feed(self, feed: object) -> dict:
        try:
            entries = await self._rss.fetch(feed.url)
        except Exception as exc:
            self._repo.update_feed_status(feed.id, "error", "连接或 XML 解析失败")
            self._repo.add_event("rss_error", f"{feed.name}：RSS 连接或解析失败", feed_id=feed.id)
            logger.warning("RSS fetch failed for feed %s: %s", feed.id, type(exc).__name__)
            raise DomainError("RSS_UNAVAILABLE", "RSS 连接或 XML 解析失败", 503) from exc
        self._repo.update_feed_status(feed.id, "connected", None)
        rules = [
            rule
            for rule in self._repo.list_subscriptions(feed.id)
            if rule.enabled and not subscription_options(rule)["archived"]
        ]
        accepted = pending = failed = 0
        config = self.get_config()
        for entry in entries:
            analysis = analyze_release(entry.title)
            release = self._repo.get_or_add_release(
                feed.id,
                entry.identity,
                {
                    "title": entry.title,
                    "download_url": entry.download_url,
                    "parsed": analysis.json(),
                },
            )
            if release.decision == "excluded":
                continue
            previous = self._repo.get_download_by_release(release.id)
            if previous and not self._can_retry(previous):
                pending += not previous.torrent_hash and previous.state in {
                    "submitted",
                    "confirming",
                }
                continue
            matches = [
                rule for rule in rules if match_subscription(analysis, rule, entry.title) is None
            ]
            if len(matches) > 1:
                self._repo.set_release_decision(release.id, "review", "多个追番规则同时匹配")
            elif not matches:
                reason = "无启用的匹配规则"
                if len(rules) == 1:
                    reason = match_subscription(analysis, rules[0], entry.title) or reason
                uncertain = (
                    analysis.episode is None
                    or analysis.title is None
                    or analysis.confidence < 45
                    or "MULTI_EPISODE_RELEASE" in analysis.warnings
                )
                self._repo.set_release_decision(
                    release.id, "review" if rules and uncertain else "skipped", reason
                )
            elif not config.enabled or not feed.enabled:
                self._repo.set_release_decision(release.id, "ready", "自动下载尚未启用")
            else:
                if previous:
                    if await self._retry_job(previous, release, matches[0]):
                        accepted += 1
                elif await self._submit(release, matches[0], config):
                    accepted += 1
                current = self._repo.get_download_by_release(release.id)
                if current:
                    pending += current.state == "confirming"
                    failed += current.state in {"retry", "missing"}
        self._repo.add_event(
            "rss_refresh",
            f"{feed.name}：读取 {len(entries)} 条，确认创建 {accepted} 条，"
            f"等待确认 {pending} 条，失败 {failed} 条",
            feed_id=feed.id,
        )
        return {
            "fetched": len(entries),
            "submitted": accepted,
            "pending": pending,
            "failed": failed,
        }

    async def _submit(
        self, release: object, rule: object, config: AutomationConfig, approved: bool = False
    ) -> bool:
        season = effective_season(rule, release.parsed.get("season"))
        options = subscription_options(rule)
        episode = release.parsed.get("episode")
        if episode is None and options["content_kind"] == "movie":
            episode = 1 - rule.episode_offset
        previous = None
        if self.operations:
            previous, reason = self.operations.revision_candidate(release, rule)
            if previous and options["downloader"] == "aria2":
                self._repo.set_release_decision(release.id, "review", "aria2 修订替换需人工处理")
                return False
            if previous and (
                reason
                or options["revision_policy"] == "keep"
                or (options["revision_policy"] == "review" and not approved)
            ):
                self._repo.set_release_decision(
                    release.id,
                    "review" if not reason else "skipped",
                    reason or "发现更高修订版，请在发布候选确认下载后替换",
                )
                return False
        folder = safe_component(rule.folder_name)
        root = config.qb_save_root
        if options["downloader"] == "aria2":
            root = self.features.private().get("aria2_save_root", "") if self.features else ""
        if not root:
            raise DomainError("DOWNLOAD_ROOT_REQUIRED", "请先配置下载器保存根目录")
        save_path = f"{root}/{folder}/Season {season}"
        local_path = (self._media_root / folder / f"Season {season}").resolve(strict=False)
        if not path_is_within(local_path, self._media_root):
            self._repo.set_release_decision(release.id, "review", "目标目录越界")
            return False
        job = self._repo.create_download(
            release.id,
            rule.id,
            (
                f"{root}/.cymediaflow-downloads/{release.id}"
                if options["downloader"] == "aria2"
                else save_path
            ),
            str(local_path),
            {
                "title": rule.title,
                "season": season,
                "episode": int(episode) + rule.episode_offset if episode is not None else None,
                "episode_offset": rule.episode_offset,
                "allow_batch": options["allow_batch"],
                "downloader": options["downloader"],
                "version": release.parsed.get("version") or 1,
                "revision_of": previous.id if previous else None,
                "revision_policy": options["revision_policy"],
                "manual": approved,
                "source_local_path": str(
                    self._media_root / ".cymediaflow-downloads" / str(release.id)
                )
                if options["downloader"] == "aria2"
                else None,
            },
        )
        self._repo.set_release_decision(release.id, "confirming", "正在提交，等待下载器确认")
        return await self._send_job(job, release.download_url)

    async def _send_job(self, job: object, url: str) -> bool:
        sending = False
        acknowledged = False
        try:
            qb = self.downloader(job)
            present = await qb.by_tag(job.qb_tag)
            if not present:
                self._repo.update_download(job.id, state="confirming", error=None)
                sending = True
                await qb.add(url, job.save_path, job.qb_tag)
                acknowledged = True
                present = await qb.by_tag(job.qb_tag)
            if present:
                return self._confirm_job(job, present)
            self._repo.set_release_decision(job.release_id, "confirming", "等待下载器创建任务")
            self._repo.add_event(
                "download_pending",
                f"任务 #{job.id} 请求已发送，等待下载器确认",
                download_id=job.id,
            )
            return False
        except Exception as exc:
            known_error = isinstance(exc, TorrentSourceError | QbittorrentError)
            definite_failure = known_error and not acknowledged
            message = str(exc) if known_error else "下载器请求失败；请同步状态核对后重试"
            state = "retry" if definite_failure or not sending else "confirming"
            self._repo.update_download(job.id, state=state, error=message)
            self._repo.set_release_decision(job.release_id, state, message)
            self._repo.add_event("download_error", f"任务 #{job.id}：{message}", download_id=job.id)
            logger.warning("Downloader add failed for job %s: %s", job.id, type(exc).__name__)
            return False

    def _confirm_job(self, job: object, matches: list[dict]) -> bool:
        if len(matches) != 1 or not matches[0].get("hash"):
            self._review(job, "下载器标签未对应唯一有效任务，请人工核对")
            return False
        self._repo.update_download(
            job.id, state="submitted", torrent_hash=str(matches[0]["hash"]), error=None
        )
        self._repo.set_release_decision(job.release_id, "queued", None)
        if not job.torrent_hash:
            self._repo.add_event(
                "download_added", f"已在下载器确认创建任务 #{job.id}", download_id=job.id
            )
        return True

    @staticmethod
    def _confirmation_expired(job: object) -> bool:
        updated = job.updated_at.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - updated).total_seconds() >= 120

    @classmethod
    def _can_retry(cls, job: object) -> bool:
        if job.torrent_hash:
            return False
        if job.state in {"planned", "retry", "missing"}:
            return True
        if job.state in {"submitted", "confirming", "retry_sync"}:
            return cls._confirmation_expired(job)
        return False

    async def _retry_job(self, job: object, release: object, rule: object) -> bool:
        previous_rule = self._repo.get_subscription(job.subscription_id)
        if job.subscription_id != rule.id and previous_rule and not previous_rule.deleted:
            return False
        # Keep the original path/naming snapshot and stable qB tag on every retry.
        self._repo.update_download(job.id, subscription_id=rule.id)
        return await self._send_job(job, release.download_url)

    async def retry_download(self, download_id: int) -> dict:
        async with self._lock:
            job = self._repo.get_download(download_id)
            if job is None:
                raise DomainError("DOWNLOAD_NOT_FOUND", "下载任务不存在", 404)
            if not self._can_retry(job):
                raise DomainError(
                    "DOWNLOAD_NOT_RETRYABLE", "任务仍在确认中或已在下载器创建，请先同步状态", 409
                )
            if job.naming_json.get("manual"):
                release = self._repo.get_release(job.release_id)
                if release is None:
                    raise DomainError("RELEASE_NOT_FOUND", "发布记录不存在", 404)
                confirmed = await self._send_job(job, release.download_url)
                current = self._repo.get_download(job.id)
                return {"confirmed": confirmed, "state": current.state, "error": current.error}
            if not self.get_config().enabled:
                raise DomainError("AUTOMATION_DISABLED", "请先在设置中启用自动追番")
            release = self._repo.get_release(job.release_id)
            feed = self._repo.get_feed(release.feed_id) if release else None
            if feed is None or feed.deleted or not feed.enabled:
                raise DomainError("FEED_DISABLED", "请先恢复并启用对应 RSS")
            matches = [
                rule
                for rule in self._repo.list_subscriptions(feed.id)
                if rule.enabled
                and match_subscription(analyze_release(release.title), rule, release.title) is None
            ]
            if len(matches) != 1:
                raise DomainError("SUBSCRIPTION_NOT_UNIQUE", "请保留一条启用且匹配此发布的追番规则")
            confirmed = await self._retry_job(job, release, matches[0])
            current = self._repo.get_download(job.id)
            return {"confirmed": confirmed, "state": current.state, "error": current.error}

    async def run_once(self) -> dict:
        if self._lock.locked():
            return {"status": "already_running"}
        async with self._lock:
            results = []
            for feed in self._repo.list_feeds():
                if not feed.enabled:
                    continue
                try:
                    results.append({"feed_id": feed.id, **await self._refresh_feed(feed)})
                except DomainError:
                    results.append({"feed_id": feed.id, "error": "RSS 刷新失败"})
            await self._sync_downloads()
            return {"status": "done", "feeds": results}

    async def sync_downloads(self) -> None:
        async with self._lock:
            await self._sync_downloads()

    async def _sync_downloads(self) -> None:
        for job in self._repo.list_pending_downloads():
            release = self._repo.get_release(job.release_id)
            rule = self._repo.get_subscription(job.subscription_id)
            feed = self._repo.get_feed(release.feed_id) if release else None
            if (
                job.state in {"retry", "planned"}
                and not job.torrent_hash
                and (job.state == "planned" or self._confirmation_expired(job))
                and release is not None
                and self.get_config().enabled
                and rule
                and not rule.deleted
                and rule.enabled
                and not subscription_options(rule)["archived"]
                and feed
                and not feed.deleted
                and feed.enabled
                and match_subscription(analyze_release(release.title), rule, release.title) is None
            ):
                await self._send_job(job, release.download_url)
                continue
            try:
                qb = self.downloader(job)
                matches = await qb.by_tag(job.qb_tag)
                if not matches:
                    if job.state not in {"missing", "retry", "planned"} and (
                        job.torrent_hash or self._can_retry(job)
                    ):
                        message = (
                            "曾创建的任务已不在下载器中，保留下载记录，请人工核对"
                            if job.torrent_hash
                            else "下载器未创建任务；请检查种子来源及 RSS 代理后重试"
                        )
                        self._repo.update_download(job.id, state="missing", error=message)
                        self._repo.set_release_decision(job.release_id, "missing", message)
                    continue
                if len(matches) != 1:
                    self._review(job, "下载器标签对应多个任务")
                    continue
                torrent = matches[0]
                if torrent.get("state") in {"pausedDL", "stoppedDL", "paused"}:
                    self._repo.update_download(job.id, state="paused")
                    continue
                if torrent.get("state") in {"error", "missingFiles"}:
                    self._review(job, "下载器报告文件或下载错误，请检查下载器")
                    continue
                torrent_hash = str(torrent.get("hash") or "")
                if not torrent_hash:
                    continue
                aria_transition = (
                    job.naming_json.get("downloader") == "aria2"
                    and torrent.get("parent_hash") == job.torrent_hash
                )
                if job.torrent_hash and job.torrent_hash != torrent_hash and not aria_transition:
                    self._review(job, "下载器任务哈希已变化，请人工核对")
                    continue
                if not job.torrent_hash:
                    self._confirm_job(job, matches)
                progress = max(0, min(100, round(float(torrent.get("progress") or 0) * 100)))
                if progress < 100:
                    self._repo.update_download(
                        job.id,
                        torrent_hash=torrent_hash,
                        state="downloading",
                        progress=progress,
                        error=None,
                    )
                    if job.progress != progress or job.state != "downloading":
                        self._repo.add_event(
                            "download_progress",
                            f"任务 #{job.id}：下载 {progress}%",
                            download_id=job.id,
                        )
                    continue
                self._repo.update_download(
                    job.id, torrent_hash=torrent_hash, state="organizing", progress=100
                )
                await self._organize(self._repo.get_download(job.id), torrent_hash, qb)
            except Exception as exc:
                logger.warning("Downloader sync failed for job %s: %s", job.id, type(exc).__name__)
                self._repo.update_download(job.id, state="retry_sync", error="下载器状态同步失败")

    def _review(self, job: object, reason: str) -> None:
        self._repo.update_download(job.id, state="review", error=reason)
        self._repo.set_release_decision(job.release_id, "review", reason)
        self._repo.add_event("review", f"任务 #{job.id}：{reason}", download_id=job.id)

    async def _organize(self, job: object, torrent_hash: str, qb: QbittorrentClient) -> None:
        if self.operations is None:
            from app.application.automation_operations import AutomationOperations
            from app.infrastructure.persistence.feature_repository import FeatureRepository

            self.operations = AutomationOperations(self, FeatureRepository(self._repo._factory))
        if not job.naming_json or "title" not in job.naming_json:
            rule = self._repo.get_subscription(job.subscription_id)
            release = self._repo.get_release(job.release_id)
            if not rule or not release:
                self._review(job, "追番规则或发布记录已丢失")
                return
            self._repo.update_download(
                job.id,
                naming_json={
                    "title": rule.title,
                    "season": effective_season(rule, release.parsed.get("season")),
                    "episode": int(release.parsed["episode"]) + rule.episode_offset,
                },
            )
            job = self._repo.get_download(job.id)
        await self.operations.auto_organize(job, qb)

    async def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._loop(), name="cymediaflow-automation")
        if self.background and self._updates_task is None:
            self._updates_task = asyncio.create_task(
                self._updates_loop(), name="cymediaflow-automation-updates"
            )

    async def stop(self) -> None:
        if self._updates_task is not None:
            self._updates_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._updates_task
            self._updates_task = None
        if self._task is not None:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    async def _updates_loop(self) -> None:
        # Slow webhook or calendar endpoints must not delay downloader reconciliation.
        while True:
            await asyncio.sleep(30)
            try:
                await self.background.tick()
            except Exception:
                logger.warning("Automation background update failed")

    async def _loop(self) -> None:
        if self._repo.list_pending_downloads():
            try:
                await self.sync_downloads()
            except Exception:
                logger.exception("Automation startup reconciliation failed")
        elapsed = 0
        while True:
            await asyncio.sleep(30)
            config = self.get_config()
            if self._repo.list_pending_downloads() and not self._lock.locked():
                try:
                    await self.sync_downloads()
                except Exception:
                    logger.warning("Download progress synchronization failed")
            if not config.enabled:
                elapsed = 0
                continue
            elapsed += 30
            if elapsed < config.interval_minutes * 60:
                continue
            elapsed = 0
            try:
                await self.run_once()
            except Exception:
                logger.exception("Automation cycle failed")
