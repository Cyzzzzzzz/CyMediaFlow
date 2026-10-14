from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

from app.core.errors import DomainError
from app.domain.automation import analyze_release
from app.infrastructure.automation.rss import HttpRssClient


class AutomationSearchService:
    def __init__(self, automation, documents, config):
        self.automation = automation
        self.documents = documents
        self.config = config

    def cached(self) -> dict:
        return self.documents.get("automation:search:last", {"items": [], "query": ""})

    async def search(self, source_id: str, query: str) -> dict:
        source = next(
            (
                s
                for s in self.config.private()["sources"]
                if s["id"] == source_id and s.get("enabled", True)
            ),
            None,
        )
        if not source:
            raise DomainError("SEARCH_SOURCE_NOT_FOUND", "搜索源不存在或已停用", 404)
        if source.get("kind") == "torznab":
            parts = urlsplit(source["url"])
            params = dict(parse_qsl(parts.query))
            params.update({"t": "search", "q": query, "limit": "100"})
            if source.get("api_key"):
                params["apikey"] = source["api_key"]
            url = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(params), ""))
        else:
            url = source["url"].replace("{query}", quote(query.strip(), safe=""))
        try:
            entries = await HttpRssClient(self.automation.get_config().rss_proxy_url or None).fetch(
                url
            )
        except Exception as exc:
            raise DomainError(
                "SEARCH_FAILED", "资源搜索失败，请检查站点、凭据和 RSS 代理", 503
            ) from exc
        repo = self.automation._repo
        feed = next((s for s in repo.list_feeds() if s.url == url), None)
        if feed is None:
            feed = repo.save_feed(
                None, {"name": f"{source['name']} · {query}", "url": url, "enabled": False}
            )
        items = []
        for entry in entries[:100]:
            release = repo.get_or_add_release(
                feed.id,
                entry.identity,
                {
                    "title": entry.title,
                    "download_url": entry.download_url,
                    "parsed": analyze_release(entry.title).json(),
                },
            )
            items.append(
                {
                    "id": release.id,
                    "title": release.title,
                    "analysis": release.parsed,
                    "decision": release.decision,
                    "feed_id": feed.id,
                }
            )
        result = {
            "source_id": source_id,
            "query": query,
            "feed_id": feed.id,
            "items": items,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        key = hashlib.sha256((source_id + "\0" + query).encode()).hexdigest()
        self.documents.put("automation:search:" + key, result)
        self.documents.put("automation:search:last", result)
        return result
