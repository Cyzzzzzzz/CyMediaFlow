from __future__ import annotations

import hashlib
import os
from pathlib import Path

from app.core.errors import DomainError
from app.core.path_safety import path_is_within
from app.domain.automation import (
    VIDEO_SUFFIXES,
    analyze_release,
    match_subscription,
    safe_relative_path,
)
from app.domain.automation_organizer import organize_plan
from app.domain.automation_subscription import effective_season, subscription_options


class AutomationOperations:
    def __init__(self, automation, documents):
        self.service = automation
        self.repo = automation._repo
        self.documents = documents

    def rule(self, rule_id: int):
        rule = self.repo.get_subscription(rule_id)
        if not rule or rule.deleted:
            raise DomainError("RULE_NOT_FOUND", "追番规则不存在", 404)
        return rule

    def job(self, job_id: int):
        job = self.repo.get_download(job_id)
        if not job:
            raise DomainError("DOWNLOAD_NOT_FOUND", "下载任务不存在", 404)
        return job

    def release(self, release_id: int):
        release = self.repo.get_release(release_id)
        if not release:
            raise DomainError("RELEASE_NOT_FOUND", "发布候选不存在", 404)
        return release

    async def download(
        self,
        release_id: int,
        subscription_id: int,
        confirm: bool = False,
        episode: int | None = None,
        season: int | None = None,
    ) -> dict:
        async with self.service._lock:
            return await self._download(release_id, subscription_id, confirm, episode, season)

    async def _download(self, release_id, subscription_id, confirm, episode=None, season=None):
        release, rule = self.release(release_id), self.rule(subscription_id)
        analysis = dict(release.parsed)
        if episode is not None:
            analysis["episode"] = episode - rule.episode_offset
        if season is not None and season != effective_season(rule, analysis.get("season")):
            raise DomainError("SEASON_MISMATCH", "请先修改此规则的目标季度")
        if analysis.get("episode") is None and not subscription_options(rule)["allow_batch"]:
            if subscription_options(rule)["content_kind"] == "movie":
                analysis["episode"] = 1 - rule.episode_offset
            else:
                raise DomainError("EPISODE_REQUIRED", "请填写集号后确认，或先为规则启用合集")
        target_episode = (
            int(analysis["episode"]) + rule.episode_offset
            if analysis.get("episode") is not None
            else None
        )
        if target_episode is not None and not 0 <= target_episode <= 999:
            raise DomainError("INVALID_EPISODE", "目标集号须介于 0 与 999")
        existing = self.repo.get_download_by_release(release_id)
        preview = {
            "release_id": release_id,
            "title": release.title,
            "target_title": rule.title,
            "season": effective_season(rule, analysis.get("season")),
            "episode": target_episode,
            "existing_job": existing.id if existing else None,
        }
        if not confirm:
            return {**preview, "confirmed": False}
        if existing:
            return {**preview, "confirmed": bool(existing.torrent_hash), "state": existing.state}
        self.repo.update_release_analysis(release_id, analysis)
        release = self.release(release_id)
        confirmed = await self.service._submit(
            release, rule, self.service.get_config(), approved=True
        )
        job = self.repo.get_download_by_release(release_id)
        return {**preview, "confirmed": confirmed, "state": job.state if job else "skipped"}

    def revision_candidate(self, release, rule):
        """One physical episode identity across feeds; only comparable language/group revisions."""
        episode = release.parsed.get("episode")
        if episode is None or "MULTI_EPISODE_RELEASE" in release.parsed.get("warnings", []):
            return None, None
        episode += rule.episode_offset
        season = effective_season(rule, release.parsed.get("season"))
        jobs = sorted(self.repo.list_downloads(limit=100000), key=lambda j: j.state != "organized")
        for job in jobs:
            old_rule = self.repo.get_subscription(job.subscription_id)
            if not old_rule or old_rule.folder_name != rule.folder_name:
                continue
            name = job.naming_json or {}
            if name.get("season") != season or name.get("episode") != episode:
                continue
            if job.state in {"removed", "superseded", "retry", "missing"}:
                continue
            old_release = self.release(job.release_id)
            if (
                old_release.parsed.get("subtitle") != release.parsed.get("subtitle")
                or old_release.parsed.get("group") != release.parsed.get("group")
                or old_release.parsed.get("resolution") != release.parsed.get("resolution")
            ):
                return job, "同一集已有其他语言、字幕组或清晰度版本，请人工选择"
            version = int(release.parsed.get("version") or 1)
            old_version = int(old_release.parsed.get("version") or 1)
            if version <= old_version:
                return job, "此季集已有相同或更高修订版"
            if job.state != "organized":
                return job, "旧版本尚未整理完成，等待完成后再替换"
            return job, None
        return None, None

    async def job_action(self, job_id: int, action: str, confirm: bool = False) -> dict:
        async with self.service._lock:
            job = self.job(job_id)
            if not job.torrent_hash:
                raise DomainError("TASK_UNCONFIRMED", "任务尚未在下载器确认")
            if action == "restore":
                return await self.restore(job, confirm)
            if action == "organize":
                if job.progress < 100:
                    raise DomainError("DOWNLOAD_INCOMPLETE", "下载完成后才能整理")
                self.repo.update_download(job.id, state="organizing", error=None)
                await self.service._organize(job, job.torrent_hash, self.service.downloader(job))
                return {"state": self.job(job.id).state}
            if action == "remove" and not confirm:
                raise DomainError("CONFIRM_REQUIRED", "请确认移除任务，媒体文件会保留")
            try:
                await self.service.downloader(job).action(job.torrent_hash, action)
            except Exception as exc:
                raise DomainError(
                    "TASK_ACTION_FAILED", "下载器操作失败，请同步状态后检查", 503
                ) from exc
            state = {
                "pause": "paused",
                "resume": "submitted",
                "recheck": "checking",
                "remove": "removed",
            }[action]
            if job.state in {"organized", "revision_ready", "superseded"} and action != "remove":
                state = job.state
            self.repo.update_download(job.id, state=state, error=None)
            self.repo.add_event("task_action", f"任务 #{job.id}：{action}", download_id=job.id)
            return {"state": state}

    def _local(self, job, relative: str) -> Path:
        path = (Path(job.local_path) / safe_relative_path(relative)).resolve(strict=False)
        if not path_is_within(path, self.service._media_root):
            raise DomainError("PATH_OUTSIDE_LIBRARY", "文件路径超出媒体目录")
        return path

    async def plan(self, job_id: int, mappings: list[dict], confirm: bool = False) -> dict:
        async with self.service._lock:
            job = self.job(job_id)
            if not job.torrent_hash or job.progress < 100:
                raise DomainError("DOWNLOAD_INCOMPLETE", "下载完成后才能预览整理")
            if self.repo.list_operations(job.id):
                raise DomainError(
                    "PLAN_EXISTS", "此任务已有整理记录，请继续整理或恢复后再操作", 409
                )
            client = self.service.downloader(job)
            try:
                files = await client.files(job.torrent_hash)
                plan = organize_plan(files, job.naming_json, mappings)
                self.validate_plan(job, plan)
            except ValueError as exc:
                raise DomainError("INVALID_ORGANIZE_PLAN", str(exc)) from exc
            if confirm:
                self.repo.plan_operations(job.id, plan)
                await self.execute_plan(job, client)
            return {"files": plan, "executed": confirm, "state": self.job(job.id).state}

    async def auto_organize(self, job, client):
        try:
            operations = self.repo.list_operations(job.id)
            if any(o.state == "restored" for o in operations):
                raise ValueError("任务已恢复原名称，请保留原名或新建下载任务")
            if not operations:
                files = await client.files(job.torrent_hash)
                if len(
                    [f for f in files if Path(f["name"]).suffix.lower() in VIDEO_SUFFIXES]
                ) > 1 and not job.naming_json.get("allow_batch"):
                    raise ValueError("多视频任务请先预览并确认文件映射")
                plan = organize_plan(files, job.naming_json)
                self.validate_plan(job, plan)
                self.repo.plan_operations(job.id, plan)
            await self.execute_plan(job, client)
            if (
                self.job(job.id).state == "revision_ready"
                and job.naming_json.get("revision_policy") == "upgrade"
            ):
                await self._revision(job.id, job.naming_json["revision_of"], True, False)
        except (ValueError, OSError, DomainError) as exc:
            self.service._review(job, str(exc)[:500])

    async def revision(self, job_id, previous_id, confirm=False, restore=False):
        async with self.service._lock:
            return await self._revision(job_id, previous_id, confirm, restore)

    async def _revision(self, job_id, previous_id, confirm, restore):
        job, old = self.job(job_id), self.job(previous_id)
        if (
            job.naming_json.get("revision_of") != old.id
            or job.local_path != old.local_path
            or job.naming_json.get("downloader", "qbittorrent") != "qbittorrent"
            or old.naming_json.get("downloader", "qbittorrent") != "qbittorrent"
        ):
            raise DomainError("INVALID_REVISION", "只有同一目录内已关联的 qB 修订版本支持替换")
        key = f"automation:revision:{job.id}"
        record = self.documents.get(key)
        if job.state == "superseded":
            raise DomainError("NEWER_REVISION_EXISTS", "请先恢复更新的版本，再操作此版本", 409)
        if record is None:
            if job.state != "revision_ready" or old.state != "organized":
                raise DomainError("REVISION_NOT_READY", "两个版本均整理完成后才能替换")
            old_files = self.repo.list_operations(old.id)
            new_files = self.repo.list_operations(job.id)
            prior_revision = self.documents.get(f"automation:revision:{old.id}")
            old_targets = (
                {r["target"] for r in prior_revision["rows"] if r["job_id"] == old.id}
                if prior_revision and prior_revision["state"] == "done"
                else {o.target_path for o in old_files}
            )
            rows = []
            for old_target in sorted(old_targets):
                rows.append(
                    {
                        "job_id": old.id,
                        "source": old_target,
                        "target": f".cymediaflow-revisions/{old.id}/{old_target}",
                    }
                )
            for op in new_files:
                marker = f".v{job.naming_json.get('version', 2)}"
                target = op.target_path.replace(marker, "", 1)
                if target not in old_targets:
                    raise DomainError(
                        "REVISION_FILE_MISMATCH", "两版文件集合不同，请人工核对字幕和视频"
                    )
                rows.append({"job_id": job.id, "source": op.target_path, "target": target})
            if len(new_files) != len(old_files):
                raise DomainError("REVISION_FILE_MISMATCH", "两版文件数量不同，请人工核对")
            record = {"rows": rows, "state": "planned", "previous_id": old.id}
        rows = record["rows"]
        if restore:
            rows = [{**r, "source": r["target"], "target": r["source"]} for r in reversed(rows)]
        if not confirm:
            return {"files": rows, "state": record["state"], "executed": False}
        self.documents.put(key, {**record, "state": "restoring" if restore else "running"})
        for row in rows:
            active = self.job(row["job_id"])
            client = self.service.downloader(active)
            actual = {f["name"] for f in await client.files(active.torrent_hash)}
            if row["target"] in actual and row["source"] not in actual:
                continue
            if row["source"] not in actual or self._local(active, row["target"]).exists():
                raise DomainError(
                    "REVISION_CONFLICT", "文件状态变化或目标已占用，停止替换；可重试或恢复", 409
                )
            target = self._local(active, row["target"])
            target.parent.mkdir(parents=True, exist_ok=True)
            if row["target"].startswith(".cymediaflow-revisions/"):
                marker = self._local(active, ".cymediaflow-revisions/.ignore")
                marker.touch(exist_ok=True)
            await client.rename_file(active.torrent_hash, row["source"], row["target"])
            actual = {f["name"] for f in await client.files(active.torrent_hash)}
            if row["target"] not in actual:
                raise DomainError("REVISION_PENDING", "等待下载器确认，请稍后重试同一操作", 409)
        self.documents.put(key, {**record, "state": "restored" if restore else "done"})
        self.repo.update_download(old.id, state="organized" if restore else "superseded")
        self.repo.update_download(job.id, state="revision_ready" if restore else "organized")
        self.repo.add_event(
            "revision",
            f"任务 #{job.id} {'恢复旧版' if restore else '替换完成，旧版已保留'}",
            download_id=job.id,
        )
        return {"executed": True}

    def validate_plan(self, job, plan):
        for row in plan:
            source, target = self._source(job, row["source"]), self._local(job, row["target"])
            if source != target and target.exists():
                raise ValueError(f"目标已存在：{row['target']}")

    def _source(self, job, relative: str) -> Path:
        root = job.naming_json.get("source_local_path")
        if not root:
            return self._local(job, relative)
        path = (Path(root) / safe_relative_path(relative)).resolve(strict=False)
        if not path_is_within(path, self.service._media_root):
            raise ValueError("源文件超出媒体目录")
        return path

    async def execute_plan(self, job, client):
        operations = self.repo.list_operations(job.id)
        aria = job.naming_json.get("downloader") == "aria2"
        for operation in operations:
            source = self._source(job, operation.source_path)
            target = self._local(job, operation.target_path)
            if source == target:
                self.repo.update_operation(operation.id, "done")
                continue
            if aria:
                # Keep aria2's seeding path intact; publish a hardlink only after completion.
                if target.exists():
                    if not source.exists() or not os.path.samefile(source, target):
                        raise ValueError("目标与原文件不一致，停止发布")
                else:
                    if not source.is_file():
                        raise ValueError("aria2 文件尚未出现在媒体挂载目录")
                    target.parent.mkdir(parents=True, exist_ok=True)
                    os.link(source, target)
            else:
                actual = {f["name"] for f in await client.files(job.torrent_hash)}
                if operation.target_path in actual and operation.source_path not in actual:
                    self.repo.update_operation(operation.id, "done")
                    continue
                if operation.source_path not in actual or target.exists():
                    raise ValueError("文件状态与整理计划冲突")
                self.repo.update_operation(operation.id, "running")
                await client.rename_file(
                    job.torrent_hash, operation.source_path, operation.target_path
                )
                actual = {f["name"] for f in await client.files(job.torrent_hash)}
                if operation.target_path not in actual:
                    raise ValueError("等待下载器确认重命名")
            self.repo.update_operation(operation.id, "done")
        if not all(self._local(job, o.target_path).is_file() for o in operations):
            self.repo.update_download(
                job.id, state="waiting_files", error="等待媒体挂载目录出现文件"
            )
            return
        state = "revision_ready" if job.naming_json.get("revision_of") else "organized"
        self.repo.update_download(job.id, state=state, error=None)
        import asyncio

        await asyncio.to_thread(self.service._catalog.list_media)
        self.repo.add_event("organized", f"任务 #{job.id} 已整理", download_id=job.id)

    async def restore(self, job, confirm: bool):
        if self.documents.get(f"automation:revision:{job.id}") or job.state == "superseded":
            raise DomainError("USE_REVISION_RESTORE", "请使用恢复旧版操作，避免破坏修订版本关系")
        if job.naming_json.get("downloader") == "aria2":
            raise DomainError("RESTORE_UNSUPPORTED", "aria2 保留了原始文件名，无需恢复源文件")
        operations = self.repo.list_operations(job.id)
        if not confirm:
            return {
                "files": [
                    {"source": o.target_path, "target": o.source_path} for o in reversed(operations)
                ],
                "executed": False,
            }
        client = self.service.downloader(job)
        for operation in reversed(operations):
            if operation.source_path == operation.target_path:
                continue
            actual = {f["name"] for f in await client.files(job.torrent_hash)}
            if operation.source_path in actual and operation.target_path not in actual:
                self.repo.update_operation(operation.id, "restored")
                continue
            if (
                self._local(job, operation.source_path).exists()
                or operation.target_path not in actual
            ):
                raise DomainError("RESTORE_CONFLICT", "原名称已占用或文件状态改变，停止恢复", 409)
            await client.rename_file(job.torrent_hash, operation.target_path, operation.source_path)
            actual = {f["name"] for f in await client.files(job.torrent_hash)}
            if operation.source_path not in actual:
                raise DomainError("RESTORE_PENDING", "等待下载器确认恢复，请稍后重试", 409)
            self.repo.update_operation(operation.id, "restored")
        self.repo.update_download(job.id, state="review", error="已恢复原文件名")
        self.repo.add_event("restored", f"任务 #{job.id} 已恢复原名称", download_id=job.id)
        return {"executed": True}

    def backfill(self, rule_id: int) -> dict:
        rule = self.rule(rule_id)
        options = subscription_options(rule)
        folder = (
            self.service._media_root / rule.folder_name / f"Season {effective_season(rule)}"
        ).resolve()
        if not path_is_within(folder, self.service._media_root):
            raise DomainError("PATH_OUTSIDE_LIBRARY", "作品目录越界")
        local = set()
        if folder.is_dir():
            for file in folder.rglob("*"):
                if (
                    file.suffix.lower() in VIDEO_SUFFIXES
                    and file.is_file()
                    and path_is_within(file.resolve(), folder)
                    and not any(p.startswith(".") for p in file.relative_to(folder).parts)
                ):
                    parsed = analyze_release(file.name)
                    if parsed.episode is not None:
                        # Standard SxxExx is already mapped; absolute release names need offset.
                        local.add(
                            parsed.episode
                            if parsed.season is not None
                            else parsed.episode + rule.episode_offset
                        )
        queued = {
            j.naming_json.get("episode")
            for j in self.repo.list_downloads(100000)
            if j.subscription_id == rule.id and j.state not in {"removed", "retry", "missing"}
        }
        candidates = {}
        for release in self.repo.list_releases(rule.feed_id, 100000):
            if release.decision == "excluded":
                continue
            parsed = analyze_release(release.title)
            if (
                match_subscription(parsed, rule, release.title) is None
                and parsed.episode is not None
            ):
                episode = parsed.episode + rule.episode_offset
                previous = candidates.get(episode)
                if not previous or (parsed.version or 1) > (previous["version"] or 1):
                    candidates[episode] = {
                        "release_id": release.id,
                        "title": release.title,
                        "version": parsed.version,
                    }
        first = options["first_episode"]
        last = (
            first + options["expected_episodes"] - 1
            if options["expected_episodes"]
            else max(
                {*local, *candidates, *(e for e in queued if e is not None)}, default=first - 1
            )
        )
        missing = [
            e for e in range(first, min(last, 999) + 1) if e not in local and e not in queued
        ]
        return {
            "subscription_id": rule.id,
            "local": sorted(local),
            "queued": sorted(e for e in queued if e is not None),
            "expected_known": options["expected_episodes"] is not None,
            "missing": [{"episode": e, "candidate": candidates.get(e)} for e in missing],
            "offset_suggestion": self.offset_suggestion(rule, candidates),
        }

    def offset_suggestion(self, rule, candidates) -> dict | None:
        releases = [
            r.parsed.get("episode")
            for r in self.repo.list_releases(rule.feed_id, 10000)
            if r.parsed.get("episode") is not None
            and match_subscription(analyze_release(r.title), rule, r.title) is None
        ]
        if not releases or min(releases) <= 1:
            return None
        return {
            "episode_offset": 1 - min(releases),
            "confidence": "low",
            "reason": f"当前 RSS 最早可见集号为 {min(releases)}，不代表本季首集；请核实后应用",
        }

    async def collect(self, rule_id: int, release_ids: list[int], confirm: bool) -> dict:
        if not confirm:
            return self.backfill(rule_id)
        async with self.service._lock:
            allowed = {
                m["candidate"]["release_id"]
                for m in self.backfill(rule_id)["missing"]
                if m["candidate"]
            }
            if not set(release_ids).issubset(allowed):
                raise DomainError("BACKFILL_CHANGED", "候选或本地文件已变化，请刷新补集预览", 409)
            results = [
                await self._download(rid, rule_id, True) for rid in dict.fromkeys(release_ids)
            ]
            return {"results": results}

    async def orphans(self) -> list[dict]:
        known = {j.torrent_hash for j in self.repo.list_downloads(100000)}
        tasks = await self.service._qb().all_tasks()
        return [
            {
                "hash": t["hash"],
                "name": t.get("name", ""),
                "save_path": t.get("save_path", ""),
                "progress": round(t.get("progress", 0) * 100),
            }
            for t in tasks
            if t["hash"] not in known
            and any(tag.strip().startswith("cymf-") for tag in t.get("tags", "").split(","))
        ]

    async def adopt(self, torrent_hash: str, subscription_id: int, episode: int, confirm: bool):
        async with self.service._lock:
            rule = self.rule(subscription_id)
            task = next((t for t in await self.orphans() if t["hash"] == torrent_hash), None)
            if task is None:
                raise DomainError("ORPHAN_NOT_FOUND", "孤儿任务不存在或已经关联", 404)
            season = effective_season(rule)
            expected = (
                f"{self.service.get_config().qb_save_root}/{rule.folder_name}/Season {season}"
            )
            if task["save_path"].rstrip("/") != expected:
                raise DomainError(
                    "ORPHAN_PATH_MISMATCH", "任务保存路径与规则目录不一致，请先在下载器调整"
                )
            if not confirm:
                return task
            identity = hashlib.sha256(("adopt:" + torrent_hash).encode()).hexdigest()
            release = self.repo.get_or_add_release(
                rule.feed_id,
                identity,
                {
                    "title": task["name"],
                    "download_url": "magnet:?xt=urn:btih:" + torrent_hash,
                    "parsed": {"title": rule.title, "episode": episode - rule.episode_offset},
                },
            )
            job = self.repo.create_download(
                release.id,
                rule.id,
                expected,
                str(self.service._media_root / rule.folder_name / f"Season {season}"),
                {
                    "title": rule.title,
                    "season": season,
                    "episode": episode,
                    "downloader": "qbittorrent",
                },
            )
            await self.service._qb().add_tag(torrent_hash, job.qb_tag)
            self.repo.update_download(job.id, state="submitted", torrent_hash=torrent_hash)
            self.repo.add_event("adopted", f"孤儿任务已关联到 #{job.id}", download_id=job.id)
            return {"id": job.id}
