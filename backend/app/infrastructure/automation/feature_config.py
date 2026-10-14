from urllib.parse import urlsplit

from sqlalchemy import func, select

from app.core.errors import DomainError
from app.infrastructure.persistence.database import AutomationEventRecord

DEFAULT_SOURCES = [
    {"id": "mikan", "name": "Mikan", "url": "https://mikanani.me/RSS/Search?searchstr={query}"},
    {"id": "nyaa", "name": "Nyaa", "url": "https://nyaa.si/?page=rss&q={query}&c=0_0&f=0"},
    {
        "id": "dmhy",
        "name": "DMHY",
        "url": "https://share.dmhy.org/topics/rss/rss.xml?keyword={query}",
    },
]


def http_url(value: str) -> str:
    try:
        parsed = urlsplit(value)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.fragment
            or any(ord(c) < 32 for c in value)
        ):
            raise ValueError()
        _ = parsed.port
    except ValueError as exc:
        raise DomainError("INVALID_URL", "请填写有效的 HTTP/HTTPS 地址，不含内嵌账号密码") from exc
    return value


class AutomationFeatureConfig:
    def __init__(self, documents):
        self.documents = documents

    def private(self) -> dict:
        return self.documents.get(
            "automation:features",
            {
                "sources": [{**s, "enabled": True, "kind": "rss"} for s in DEFAULT_SOURCES],
                "aria2_url": "",
                "aria2_save_root": "",
                "webhook_enabled": False,
                "webhook_events": ["download_added", "organized", "review", "download_error"],
                "llm_enabled": False,
                "llm_url": "",
                "llm_model": "",
                "version_auto_check": False,
            },
        )

    def public(self) -> dict:
        config = self.private()
        public = {
            k: v
            for k, v in config.items()
            if k
            not in {
                "sources",
                "aria2_secret",
                "webhook_secret",
                "llm_api_key",
                "webhook_url",
            }
        }
        public["sources"] = [
            {
                "id": s["id"],
                "name": s["name"],
                "kind": s.get("kind", "rss"),
                "enabled": s.get("enabled", True),
                "address": urlsplit(s["url"]).hostname,
                "api_key_configured": bool(s.get("api_key")),
            }
            for s in config["sources"]
        ]
        for field in ("aria2_secret", "webhook_secret", "llm_api_key", "webhook_url"):
            public[field + "_configured"] = bool(config.get(field))
        return public

    def save(self, values: dict) -> dict:
        old = self.private()
        webhook_was_enabled = old.get("webhook_enabled", False)
        sources = values.pop("sources", None)
        if sources is not None:
            previous = {s["id"]: s for s in old["sources"]}
            if len({s["id"] for s in sources}) != len(sources):
                raise DomainError("DUPLICATE_SOURCE", "搜索源 ID 不能重复")
            for source in sources:
                existing = previous.get(source["id"], {})
                source["url"] = source.get("url") or existing.get("url", "")
                http_url(source["url"])
                if source["kind"] == "rss" and source["url"].count("{query}") != 1:
                    raise DomainError("INVALID_SEARCH_TEMPLATE", "RSS 搜索地址须包含一个 {query}")
                source["api_key"] = (
                    ""
                    if source.pop("clear_api_key", False)
                    else source.get("api_key")
                    if source.get("api_key") is not None
                    else existing.get("api_key", "")
                )
            old["sources"] = sources
        for key in ("aria2_secret", "webhook_secret", "llm_api_key"):
            if values.pop("clear_" + key, False):
                values[key] = ""
            elif values.get(key) is None:
                values.pop(key, None)
        if values.get("webhook_url") is None:
            values.pop("webhook_url", None)
        old.update(values)
        for key in ("aria2_url", "webhook_url", "llm_url"):
            if old.get(key):
                http_url(old[key])
        root = old.get("aria2_save_root", "")
        if root and (not root.startswith("/") or ".." in root.split("/")):
            raise DomainError("INVALID_DOWNLOAD_ROOT", "aria2 目录须为绝对 POSIX 路径")
        if old.get("webhook_enabled") and not old.get("webhook_url"):
            raise DomainError("WEBHOOK_NOT_CONFIGURED", "请先配置通知 Webhook 地址")
        if old.get("llm_enabled") and not all(old.get(k) for k in ("llm_url", "llm_model")):
            raise DomainError("LLM_NOT_CONFIGURED", "请先配置辅助解析服务和模型")
        if old.get("webhook_enabled") and not webhook_was_enabled:
            with self.documents.factory() as session:
                last = session.scalar(select(func.max(AutomationEventRecord.id))) or 0
            self.documents.put("automation:webhook:cursor", {"id": last})
        self.documents.put("automation:features", old)
        return self.public()
