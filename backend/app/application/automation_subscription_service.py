from __future__ import annotations

import asyncio

from app.application.automation_service import AutomationService, public_feed, public_subscription
from app.application.ports import MetadataProviderPort
from app.core.errors import DomainError
from app.domain.automation import analyze_release, normalized_title
from app.infrastructure.automation.rss import validate_feed_url


class AutomationSubscriptionService:
    """Analyze first, edit a draft, then atomically subscribe. Analysis never adds downloads."""

    metadata_budget_seconds = 25

    def __init__(self, automation: AutomationService, providers: dict[str, MetadataProviderPort]):
        self._automation = automation
        self._providers = providers

    async def metadata_search(self, provider: str, query: str) -> list[dict]:
        selected = self._providers.get(provider)
        if selected is None:
            raise DomainError("INVALID_PROVIDER", "不支持的匹配来源")
        if not query.strip():
            raise DomainError("EMPTY_QUERY", "请输入作品搜索关键词")
        try:
            candidates = await asyncio.wait_for(selected.search(query.strip(), limit=6), timeout=20)
        except DomainError:
            raise
        except Exception as exc:
            raise DomainError(
                "METADATA_UNAVAILABLE", "作品搜索暂不可用，请检查对应来源配置", 503
            ) from exc
        return [
            {
                "provider": item.provider,
                "external_id": item.external_id,
                "title": item.title,
                "original_title": item.original_title,
                "year": item.year,
                "image_url": item.image_url,
            }
            for item in candidates
        ]

    async def analyze(self, url: str, parser: str) -> dict:
        try:
            url = validate_feed_url(url)
        except ValueError as exc:
            raise DomainError("INVALID_FEED_URL", str(exc)) from exc
        try:
            entries = await asyncio.wait_for(self._automation._rss.fetch(url), timeout=25)
        except Exception as exc:
            raise DomainError(
                "RSS_UNAVAILABLE", "RSS 连接或解析失败，请检查地址及 RSS 代理", 503
            ) from exc
        grouped: dict[tuple, dict] = {}
        unrecognized = 0
        for entry in entries:
            analysis = analyze_release(entry.title)
            if (
                not analysis.title
                or analysis.episode is None
                or analysis.confidence < 45
                or "MULTI_EPISODE_RELEASE" in analysis.warnings
            ):
                unrecognized += 1
                continue
            key = (
                analysis.title,
                analysis.season if analysis.season is not None else 1,
                analysis.group,
                analysis.resolution,
                analysis.subtitle,
            )
            if key not in grouped:
                grouped[key] = {
                    "rule": {
                        "title": analysis.title,
                        "source_title": analysis.title,
                        "folder_name": "",
                        "aliases": [analysis.title],
                        "season": analysis.season if analysis.season is not None else 1,
                        "episode_offset": 0,
                        "season_offset": 0,
                        "preferred_group": analysis.group,
                        "preferred_resolution": analysis.resolution,
                        "preferred_subtitle": analysis.subtitle
                        if analysis.subtitle in {"CHS", "CHT"}
                        else None,
                        "exclude_keywords": [],
                        "enabled": True,
                        "year": analysis.year,
                        "source": analysis.source,
                        "resolution": analysis.resolution,
                        "subtitle": analysis.subtitle,
                        "release_group": analysis.group,
                    },
                    "entry_count": 0,
                    "examples": [],
                    "matches": [],
                    "warning": None,
                }
            group = grouped[key]
            group["entry_count"] += 1
            if len(group["examples"]) < 3:
                group["examples"].append(entry.title)

        candidates = list(grouped.values())[:30]
        if parser != "parser":
            semaphore = asyncio.Semaphore(3)
            titles = {group["rule"]["title"] for group in candidates}

            async def search(title: str) -> tuple[str, list[dict], str | None]:
                async with semaphore:
                    try:
                        return title, await self.metadata_search(parser, title), None
                    except Exception:
                        return title, [], f"{parser.upper()} 匹配暂不可用，可手动确认或稍后重新搜索"

            matches_by_title = {
                title: ([], "元数据匹配超时，可手动搜索；发布解析结果已保留") for title in titles
            }
            tasks = [asyncio.create_task(search(title)) for title in titles]
            try:
                if tasks:
                    done, _ = await asyncio.wait(tasks, timeout=self.metadata_budget_seconds)
                    for task in done:
                        title, matches, warning = task.result()
                        matches_by_title[title] = (matches, warning)
            finally:
                for task in tasks:
                    if not task.done():
                        task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
            for group in candidates:
                rule = group["rule"]
                matches, warning = matches_by_title[rule["title"]]
                group["matches"], group["warning"] = matches, warning
                if not matches:
                    group["warning"] = warning or "未找到元数据匹配，可在弹窗中手动搜索"
                    continue
                exact_matches = [
                    item
                    for item in matches
                    if normalized_title(rule["title"])
                    in {
                        normalized_title(item["title"]),
                        normalized_title(item["original_title"] or ""),
                    }
                    and (not rule["year"] or item["year"] == rule["year"])
                ]
                exact = exact_matches[0] if len(exact_matches) == 1 else None
                # Fuzzy candidates require confirmation; never silently choose an unrelated work.
                if exact:
                    rule.update(
                        title=exact["title"],
                        year=exact["year"] or rule["year"],
                        poster_url=exact["image_url"],
                        provider=exact["provider"],
                        provider_id=exact["external_id"],
                    )
                else:
                    group["warning"] = "找到候选作品，请选择正确条目确认海报和名称"
        return {
            "candidates": candidates,
            "total_entries": len(entries),
            "unrecognized": unrecognized,
            "truncated": len(grouped) > len(candidates),
        }

    def subscribe(self, url: str, name: str, rules: list[dict]) -> dict:
        try:
            url = validate_feed_url(url)
        except ValueError as exc:
            raise DomainError("INVALID_FEED_URL", str(exc)) from exc
        prepared = [self._automation.prepare_subscription(rule) for rule in rules]
        feed, records, created = self._automation._repo.subscribe_feed(
            {"url": url, "name": name.strip() or rules[0]["title"], "enabled": True}, prepared
        )
        self._automation._repo.add_event(
            "subscribed", f"{feed.name}：新增 {created} 条追番规则", feed_id=feed.id
        )
        return {
            "feed": public_feed(feed),
            "rules": [public_subscription(record) for record in records],
            "created": created,
            "automation_enabled": self._automation.get_config().enabled,
        }
