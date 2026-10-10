from __future__ import annotations

import hashlib
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse
from xml.etree import ElementTree as ET

import httpx

MAX_FEED_BYTES = 2 * 1024 * 1024
ATOM = "{http://www.w3.org/2005/Atom}"


@dataclass(frozen=True, slots=True)
class FeedEntry:
    identity: str
    title: str
    download_url: str


def validate_feed_url(url: str) -> str:
    parsed = urlparse(url.strip())
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or any(ord(char) < 32 for char in url)
    ):
        raise ValueError("RSS 地址必须是 HTTP 或 HTTPS URL")
    return url.strip()


def parse_feed(content: bytes, base_url: str) -> list[FeedEntry]:
    if len(content) > MAX_FEED_BYTES:
        raise ValueError("RSS 超过 2 MiB 限制")
    try:
        root = ET.fromstring(content)
    except ET.ParseError as exc:
        raise ValueError("RSS XML 无效") from exc
    if root.tag in {"rss", "RDF", "{http://www.w3.org/1999/02/22-rdf-syntax-ns#}RDF"}:
        nodes = root.findall(".//item")
        rows = [
            (
                n.findtext("title") or "",
                n.findtext("guid") or "",
                next((e.get("url", "") for e in n.findall("enclosure") if e.get("url")), "")
                or n.findtext("link")
                or "",
            )
            for n in nodes
        ]
    elif root.tag == f"{ATOM}feed":
        nodes = root.findall(f"{ATOM}entry")
        rows = []
        for n in nodes:
            links = n.findall(f"{ATOM}link")
            selected = next(
                (link.get("href", "") for link in links if link.get("rel") == "enclosure"), ""
            )
            selected = selected or next(
                (link.get("href", "") for link in links if link.get("rel") in {None, "alternate"}),
                "",
            )
            rows.append((n.findtext(f"{ATOM}title") or "", n.findtext(f"{ATOM}id") or "", selected))
    else:
        raise ValueError("只支持 RSS 或 Atom 订阅")
    result: list[FeedEntry] = []
    seen: set[str] = set()
    for title, guid, raw_url in rows[:500]:
        link = urljoin(base_url, raw_url.strip())
        scheme = urlparse(link).scheme
        if not title.strip() or scheme not in {"http", "https", "magnet"}:
            continue
        identity = hashlib.sha256((guid.strip() or link).encode("utf-8")).hexdigest()
        if identity not in seen:
            result.append(FeedEntry(identity, title.strip(), link))
            seen.add(identity)
    return result


class HttpRssClient:
    def __init__(self, proxy_url: str | None = None) -> None:
        self._proxy_url = proxy_url

    async def fetch(self, url: str) -> list[FeedEntry]:
        validate_feed_url(url)
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(20.0),
            proxy=self._proxy_url,
            follow_redirects=True,
            trust_env=False,
            headers={"User-Agent": "CyMediaFlow/0.1 RSS"},
        ) as client, client.stream("GET", url) as response:
            response.raise_for_status()
            chunks: list[bytes] = []
            size = 0
            async for chunk in response.aiter_bytes():
                size += len(chunk)
                if size > MAX_FEED_BYTES:
                    raise ValueError("RSS 超过 2 MiB 限制")
                chunks.append(chunk)
            return parse_feed(b"".join(chunks), str(response.url))
