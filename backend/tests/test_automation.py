from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock

import httpx
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.domain.automation import analyze_release, match_subscription, safe_relative_path
from app.infrastructure.automation.qbittorrent import QbittorrentClient
from app.infrastructure.automation.rss import FeedEntry, parse_feed
from app.main import create_app


class FakeQbittorrent:
    def __init__(self, media_root: Path) -> None:
        self.media_root = media_root
        self.added: list[tuple[str, str, str]] = []
        self.paths: list[str] = []
        self.tag = ""

    async def by_tag(self, tag: str) -> list[dict]:
        return [{"hash": "fake-hash", "progress": 1.0}] if tag == self.tag else []

    async def add(self, url: str, save_path: str, tag: str) -> bool:
        self.added.append((url, save_path, tag))
        self.tag = tag
        local = self.media_root / "Hero" / "Season 1"
        local.mkdir(parents=True, exist_ok=True)
        (local / "[ANi] Hero - 01 [1080P].mkv").write_bytes(b"video")
        (local / "[ANi] Hero - 01.chs.ass").write_bytes(b"subtitle")
        self.paths = ["[ANi] Hero - 01 [1080P].mkv", "[ANi] Hero - 01.chs.ass"]
        return True

    async def files(self, _hash: str) -> list[dict]:
        return [{"name": name} for name in self.paths]

    async def rename_file(self, _hash: str, source: str, target: str) -> None:
        local = self.media_root / "Hero" / "Season 1"
        (local / source).rename(local / target)
        self.paths[self.paths.index(source)] = target


def app_settings(tmp_path: Path) -> Settings:
    media = tmp_path / "media"
    media.mkdir()
    return Settings(
        media_root=media,
        allowed_media_root=media,
        data_dir=tmp_path / "data",
        bangumi_token_file=tmp_path / "missing.json",
        ignore_marker_enabled=False,
    )


def test_rss_rss_atom_and_release_policy() -> None:
    rss = (
        b"<rss><channel><item><title>[ANi] Hero - 01 [1080P].mkv</title>"
        b'<guid>episode-1</guid><enclosure url="magnet:?xt=urn:btih:abc" />'
        b"</item></channel></rss>"
    )
    entries = parse_feed(rss, "https://example.org/feed")
    assert len(entries) == 1
    assert entries[0].download_url.startswith("magnet:")
    atom = (
        b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Hero - 02</title>'
        b'<id>episode-2</id><link rel="enclosure" href="https://a.test/a.torrent" />'
        b"</entry></feed>"
    )
    assert parse_feed(atom, "https://a.test/")[0].title == "Hero - 02"
    analysis = analyze_release("[ANi] Hero - 01 [1080P].mkv")
    rule = type(
        "Rule",
        (),
        {
            "title": "Hero",
            "aliases": [],
            "preferred_group": "ANi",
            "preferred_resolution": "1080p",
            "exclude_keywords": [],
            "episode_offset": 0,
        },
    )()
    assert match_subscription(analysis, rule, "[ANi] Hero - 01 [1080P].mkv") is None
    assert match_subscription(analysis, rule, "Hero 720p") is None
    assert analyze_release("Hero - 01-03").episode is None
    try:
        safe_relative_path("../outside.mkv")
    except ValueError:
        pass
    else:
        raise AssertionError("path traversal was accepted")
    for unsafe in ("C:/outside.mkv", "folder/../outside.mkv", "/outside.mkv"):
        try:
            safe_relative_path(unsafe)
        except ValueError:
            pass
        else:
            raise AssertionError(f"unsafe path accepted: {unsafe}")


def test_qbittorrent_adapter_login_and_file_rename(monkeypatch) -> None:
    from app.infrastructure.automation import qbittorrent as qb_module

    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path.endswith("/auth/login"):
            return httpx.Response(200, text="Ok.", headers={"set-cookie": "SID=test; Path=/"})
        assert request.headers.get("cookie") == "SID=test"
        if request.url.path.endswith("/app/version"):
            return httpx.Response(200, text="5.1.0")
        if request.url.path.endswith("/torrents/add"):
            return httpx.Response(200, text="Ok.")
        if request.url.path.endswith("/torrents/info"):
            return httpx.Response(200, json=[{"hash": "test", "progress": 1.0}])
        if request.url.path.endswith("/torrents/files"):
            return httpx.Response(200, json=[{"name": "episode.mkv"}])
        if request.url.path.endswith("/torrents/renameFile"):
            return httpx.Response(200)
        raise AssertionError(request.url.path)

    original_client = httpx.AsyncClient
    monkeypatch.setattr(
        qb_module.httpx,
        "AsyncClient",
        lambda **kwargs: original_client(transport=httpx.MockTransport(handler), **kwargs),
    )

    async def exercise() -> None:
        qb = QbittorrentClient("http://127.0.0.1:8080", "admin", "secret")
        assert await qb.test_connection() == "5.1.0"
        assert await qb.add("magnet:?xt=urn:btih:test", "/downloads", "cymf-1")
        assert (await qb.by_tag("cymf-1"))[0]["hash"] == "test"
        assert (await qb.files("test"))[0]["name"] == "episode.mkv"
        await qb.rename_file("test", "episode.mkv", "Hero S01E01.mkv")

    asyncio.run(exercise())
    assert len(calls) == 10


def test_deleted_feed_can_be_added_again(tmp_path: Path) -> None:
    settings = app_settings(tmp_path)
    with TestClient(create_app(settings)) as client:
        payload = {"name": "RSS", "url": "https://example.org/feed?passkey=secret"}
        first = client.post("/api/v1/automation/feeds", json=payload).json()["data"]
        assert "passkey" not in first["url"]
        assert client.delete(f"/api/v1/automation/feeds/{first['id']}").status_code == 200
        second = client.post("/api/v1/automation/feeds", json=payload).json()["data"]
        assert first["id"] == second["id"]
        invalid = client.post(
            "/api/v1/automation/feeds",
            json={"name": "bad", "url": "file:///etc/passwd"},
        )
        assert invalid.status_code == 400


def test_ambiguous_release_stays_in_review(tmp_path: Path) -> None:
    settings = app_settings(tmp_path)
    with TestClient(create_app(settings)) as client:
        automation = client.app.state.container.automation_service
        automation._rss.fetch = AsyncMock(
            return_value=[FeedEntry("ambiguous", "Hero - 01-03", "magnet:?xt=urn:btih:abc")]
        )
        feed = client.post(
            "/api/v1/automation/feeds", json={"name": "RSS", "url": "https://example.org/rss"}
        ).json()["data"]
        client.post(
            "/api/v1/automation/subscriptions",
            json={"feed_id": feed["id"], "title": "Hero", "folder_name": "Hero"},
        )
        result = client.post(f"/api/v1/automation/feeds/{feed['id']}/refresh")
        assert result.json()["data"]["submitted"] == 0
        releases = client.get("/api/v1/automation/releases").json()["data"]
        assert releases[0]["decision"] == "review"
        assert client.get("/api/v1/automation/downloads").json()["data"] == []


def test_cannot_clear_downloader_password_while_enabled(tmp_path: Path) -> None:
    settings = app_settings(tmp_path)
    with TestClient(create_app(settings)) as client:
        initial = {
            "enabled": True,
            "qb_url": "http://127.0.0.1:8080",
            "qb_username": "admin",
            "qb_save_root": "/downloads/Bangumi",
            "qb_password": "secret",
        }
        assert client.put("/api/v1/automation/settings", json=initial).status_code == 200
        invalid = client.put(
            "/api/v1/automation/settings",
            json={**initial, "clear_qb_password": True},
        )
        assert invalid.status_code == 400
        assert client.get("/api/v1/automation/settings").json()["data"]["qb_password_configured"]


def test_automation_rss_to_qb_to_safe_rename_and_media_scan(tmp_path: Path) -> None:
    settings = app_settings(tmp_path)
    with TestClient(create_app(settings)) as client:
        automation = client.app.state.container.automation_service
        fake = FakeQbittorrent(settings.media_root)
        automation._rss.fetch = AsyncMock(
            return_value=[
                FeedEntry("id-01", "[ANi] Hero - 01 [1080P].mkv", "magnet:?xt=urn:btih:abc")
            ]
        )
        automation._qb = lambda: fake
        feed = client.post(
            "/api/v1/automation/feeds",
            json={
                "name": "Hero RSS",
                "url": "https://example.org/feed?passkey=secret",
                "enabled": True,
            },
        ).json()["data"]
        assert "secret" not in feed["url"]
        subscription = client.post(
            "/api/v1/automation/subscriptions",
            json={
                "feed_id": feed["id"],
                "title": "Hero",
                "folder_name": "Hero",
                "season": 1,
                "preferred_group": "ANi",
                "preferred_resolution": "1080p",
            },
        ).json()["data"]
        assert subscription["title"] == "Hero"
        preview = client.post(f"/api/v1/automation/feeds/{feed['id']}/preview")
        assert preview.status_code == 200
        assert preview.json()["data"][0]["analysis"]["episode"] == 1
        disabled = client.post(f"/api/v1/automation/feeds/{feed['id']}/refresh")
        assert disabled.json()["data"]["submitted"] == 0
        assert client.get("/api/v1/automation/downloads").json()["data"] == []
        config = client.put(
            "/api/v1/automation/settings",
            json={
                "enabled": True,
                "interval_minutes": 15,
                "qb_url": "http://127.0.0.1:8080",
                "qb_username": "admin",
                "qb_password": "secret",
                "qb_save_root": "/downloads/Bangumi",
            },
        )
        assert config.status_code == 200
        assert "secret" not in config.text
        first = client.post(f"/api/v1/automation/feeds/{feed['id']}/refresh")
        assert first.json()["data"]["submitted"] == 1
        assert fake.added[0][1] == "/downloads/Bangumi/Hero/Season 1"
        second = client.post(f"/api/v1/automation/feeds/{feed['id']}/refresh")
        assert second.json()["data"]["submitted"] == 0
        assert len(fake.added) == 1
        sync = client.post("/api/v1/automation/downloads/sync")
        assert sync.status_code == 200
        job = client.get("/api/v1/automation/downloads").json()["data"][0]
        assert job["state"] == "organized"
        assert (
            settings.media_root / "Hero" / "Season 1" / "Hero S01E01.mkv"
        ).read_bytes() == b"video"
        assert (
            settings.media_root / "Hero" / "Season 1" / "Hero S01E01.sc.ass"
        ).read_bytes() == b"subtitle"
        assert client.get("/api/v1/media").json()["data"][0]["title"] == "Hero"
        assert client.get("/api/v1/automation/events").json()["data"][0]["kind"] == "organized"


def test_automation_rejects_duplicate_target_without_overwriting(tmp_path: Path) -> None:
    settings = app_settings(tmp_path)
    with TestClient(create_app(settings)) as client:
        automation = client.app.state.container.automation_service
        fake = FakeQbittorrent(settings.media_root)
        automation._rss.fetch = AsyncMock(
            return_value=[
                FeedEntry("one", "[ANi] Hero - 01 [1080P].mkv", "magnet:?xt=urn:btih:abc")
            ]
        )
        automation._qb = lambda: fake
        feed = client.post(
            "/api/v1/automation/feeds",
            json={
                "name": "RSS",
                "url": "https://example.org/rss",
            },
        ).json()["data"]
        client.post(
            "/api/v1/automation/subscriptions",
            json={
                "feed_id": feed["id"],
                "title": "Hero",
                "folder_name": "Hero",
            },
        )
        client.put(
            "/api/v1/automation/settings",
            json={
                "enabled": True,
                "qb_url": "http://127.0.0.1:8080",
                "qb_username": "admin",
                "qb_password": "secret",
                "qb_save_root": "/downloads/Bangumi",
            },
        )
        client.post(f"/api/v1/automation/feeds/{feed['id']}/refresh")
        target = settings.media_root / "Hero" / "Season 1" / "Hero S01E01.mkv"
        target.write_bytes(b"existing")
        client.post("/api/v1/automation/downloads/sync")
        job = client.get("/api/v1/automation/downloads").json()["data"][0]
        assert job["state"] == "review"
        assert target.read_bytes() == b"existing"
        assert fake.paths[0] == "[ANi] Hero - 01 [1080P].mkv"
