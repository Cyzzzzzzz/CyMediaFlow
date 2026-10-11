from __future__ import annotations

import asyncio
import json
import logging
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from app.core.errors import DomainError
from app.core.path_safety import path_is_within
from app.domain.automation import (
    SUBTITLE_SUFFIXES,
    VIDEO_SUFFIXES,
    analyze_release,
    match_subscription,
    safe_component,
    safe_relative_path,
    subtitle_tag,
    target_stem,
)
from app.domain.automation_subscription import (
    effective_season,
    split_subscription_values,
    subscription_options,
    valid_poster_url,
)
from app.domain.keywords import normalize_keywords
from app.infrastructure.automation.qbittorrent import QbittorrentClient
from app.infrastructure.automation.rss import HttpRssClient, validate_feed_url
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
        if enabled and (
            not qb_url or not qb_save_root or not qb_username or not effective_password
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
        return QbittorrentClient(config.qb_url, config.qb_username, password)

    async def test_downloader(self) -> str:
        try:
            return await self._qb().test_connection()
        except DomainError:
            raise
        except Exception as exc:
            raise DomainError("DOWNLOADER_UNAVAILABLE", "qBittorrent 连接测试失败", 503) from exc

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
        accepted = 0
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
            if self._repo.get_download_by_release(release.id):
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
                if await self._submit(release, matches[0], config):
                    accepted += 1
        self._repo.add_event(
            "rss_refresh",
            f"{feed.name}：读取 {len(entries)} 条，提交 {accepted} 条",
            feed_id=feed.id,
        )
        return {"fetched": len(entries), "submitted": accepted}

    async def _submit(self, release: object, rule: object, config: AutomationConfig) -> bool:
        season = effective_season(rule, release.parsed.get("season"))
        folder = safe_component(rule.folder_name)
        save_path = f"{config.qb_save_root}/{folder}/Season {season}"
        local_path = (self._media_root / folder / f"Season {season}").resolve(strict=False)
        if not path_is_within(local_path, self._media_root):
            self._repo.set_release_decision(release.id, "review", "目标目录越界")
            return False
        job = self._repo.create_download(
            release.id,
            rule.id,
            save_path,
            str(local_path),
            {
                "title": rule.title,
                "season": season,
                "episode": int(release.parsed["episode"]) + rule.episode_offset,
            },
        )
        self._repo.set_release_decision(release.id, "queued", None)
        return await self._send_job(job, release.download_url)

    async def _send_job(self, job: object, url: str) -> bool:
        try:
            qb = self._qb()
            present = await qb.by_tag(job.qb_tag)
            if not present:
                await qb.add(url, job.save_path, job.qb_tag)
            self._repo.update_download(job.id, state="submitted", error=None)
            self._repo.add_event(
                "download_added", f"已向 qBittorrent 提交任务 #{job.id}", download_id=job.id
            )
            return True
        except Exception as exc:
            self._repo.update_download(job.id, state="retry", error="下载器添加失败；待重试")
            self._repo.add_event(
                "download_error", f"任务 #{job.id} 添加失败；待重试", download_id=job.id
            )
            logger.warning("Downloader add failed for job %s: %s", job.id, type(exc).__name__)
            return False

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
            if job.state == "retry" and release is not None:
                await self._send_job(job, release.download_url)
                continue
            try:
                qb = self._qb()
                matches = await qb.by_tag(job.qb_tag)
                if not matches:
                    continue
                if len(matches) != 1:
                    self._review(job, "下载器标签对应多个任务")
                    continue
                torrent = matches[0]
                torrent_hash = str(torrent.get("hash") or "")
                if not torrent_hash:
                    continue
                progress = max(0, min(100, round(float(torrent.get("progress") or 0) * 100)))
                if progress < 100:
                    self._repo.update_download(
                        job.id, torrent_hash=torrent_hash, state="downloading", progress=progress
                    )
                    continue
                self._repo.update_download(
                    job.id, torrent_hash=torrent_hash, state="organizing", progress=100
                )
                await self._organize(job, torrent_hash, qb)
            except Exception as exc:
                logger.warning("Downloader sync failed for job %s: %s", job.id, type(exc).__name__)
                self._repo.update_download(job.id, state="retry_sync", error="下载器状态同步失败")

    def _review(self, job: object, reason: str) -> None:
        self._repo.update_download(job.id, state="review", error=reason)
        self._repo.add_event("review", f"任务 #{job.id}：{reason}", download_id=job.id)

    async def _organize(self, job: object, torrent_hash: str, qb: QbittorrentClient) -> None:
        files = await qb.files(torrent_hash)
        videos = [
            file
            for file in files
            if Path(str(file.get("name", ""))).suffix.casefold() in VIDEO_SUFFIXES
        ]
        if len(videos) != 1:
            self._review(job, "需要恰好一个视频文件；合集或多视频请人工处理")
            return
        rule = self._repo.get_subscription(job.subscription_id)
        release = self._repo.get_release(job.release_id)
        if rule is None or release is None:
            self._review(job, "追番规则或发布记录已丢失")
            return
        try:
            video_path = safe_relative_path(str(videos[0]["name"]))
            local_dir = Path(job.local_path).resolve(strict=False)
            if not path_is_within(local_dir, self._media_root):
                raise ValueError("本地下载目录越界")
            if len(video_path.parts) != 1:
                raise ValueError("多层种子文件目录需要人工整理")
            # New rule edits affect future downloads, never an already queued task's target.
            naming = job.naming_json or {}
            episode = int(
                naming.get("episode", int(release.parsed["episode"]) + rule.episode_offset)
            )
            season = int(naming.get("season", effective_season(rule, release.parsed.get("season"))))
            if episode < 0:
                raise ValueError("调整后的集号无效")
            stem = target_stem(naming.get("title", rule.title), season, episode)
            media_files = [
                file
                for file in files
                if Path(str(file.get("name", ""))).suffix.casefold()
                in VIDEO_SUFFIXES | SUBTITLE_SUFFIXES
            ]
            planned: list[tuple[str, str]] = []
            for file in media_files:
                original = safe_relative_path(str(file["name"]))
                if len(original.parts) != 1:
                    raise ValueError("字幕与视频不在同一层目录")
                suffix = original.suffix.casefold()
                tag = subtitle_tag(original.name) if suffix in SUBTITLE_SUFFIXES else ""
                planned.append((original.as_posix(), stem + tag + suffix))
            targets = [target.casefold() for _, target in planned]
            if len(targets) != len(set(targets)):
                raise ValueError("多个文件将生成相同目标名称")
            occupied = {str(file.get("name", "")).casefold() for file in files}
            for source, target in planned:
                target_path = (local_dir / target).resolve(strict=False)
                if not path_is_within(target_path, self._media_root):
                    raise ValueError("目标文件越界")
                if target.casefold() != source.casefold() and (
                    target.casefold() in occupied or target_path.exists()
                ):
                    raise ValueError("目标文件已存在")
        except (KeyError, TypeError, ValueError) as exc:
            self._review(job, str(exc))
            return
        operations = self._repo.list_operations(job.id)
        if not operations:
            for source, target in planned:
                self._repo.plan_operation(job.id, source, target)
            operations = self._repo.list_operations(job.id)
        for operation in operations:
            actual = {str(file.get("name", "")) for file in await qb.files(torrent_hash)}
            if operation.target_path in actual and operation.source_path not in actual:
                self._repo.update_operation(operation.id, "done")
                continue
            if operation.source_path == operation.target_path:
                self._repo.update_operation(operation.id, "done")
                continue
            if operation.source_path not in actual or operation.target_path in actual:
                self._review(job, "下载器文件状态与重命名计划冲突")
                return
            self._repo.update_operation(operation.id, "running")
            await qb.rename_file(torrent_hash, operation.source_path, operation.target_path)
            actual = {str(file.get("name", "")) for file in await qb.files(torrent_hash)}
            if operation.target_path not in actual:
                self._repo.update_download(job.id, state="retry_sync", error="等待下载器确认重命名")
                return
            self._repo.update_operation(operation.id, "done")
        if not all(
            (Path(job.local_path) / operation.target_path).is_file() for operation in operations
        ):
            self._repo.update_download(
                job.id, state="waiting_files", error="等待媒体目录出现下载文件"
            )
            return
        self._repo.update_download(job.id, state="organized", error=None)
        await asyncio.to_thread(self._catalog.list_media)
        self._repo.add_event(
            "organized", f"任务 #{job.id} 已整理并刷新媒体列表", download_id=job.id
        )

    async def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._loop(), name="cymediaflow-automation")

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    async def _loop(self) -> None:
        if self.get_config().enabled:
            try:
                await self.sync_downloads()
            except Exception:
                logger.exception("Automation startup reconciliation failed")
        elapsed = 0
        while True:
            await asyncio.sleep(30)
            config = self.get_config()
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
