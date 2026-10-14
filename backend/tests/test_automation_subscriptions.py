from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import text

from app.api.automation_schemas import SubscriptionDraft
from app.domain.artwork import RemoteArtwork
from app.domain.automation import analyze_release, match_subscription
from app.domain.media import MetadataCandidate
from app.infrastructure.automation.rss import FeedEntry
from app.infrastructure.persistence.database import initialize_database
from app.main import create_app
from tests.test_automation import FakeQbittorrent, app_settings


def candidate(title="Hero", external_id="12") -> MetadataCandidate:
    return MetadataCandidate(
        provider="bangumi",
        external_id=external_id,
        title=title,
        original_title=title,
        year=2026,
        episode_count=12,
        image_url="https://lain.bgm.tv/pic/cover/l/hero.jpg",
        summary="A test anime",
    )


def draft(**overrides) -> dict:
    return SubscriptionDraft(title="Hero", **overrides).model_dump()


def test_analyze_is_read_only_and_confirms_atomically_idempotently(tmp_path: Path) -> None:
    with TestClient(create_app(app_settings(tmp_path))) as client:
        container = client.app.state.container
        automation = container.automation_service
        automation._rss.fetch = AsyncMock(
            return_value=[
                FeedEntry("1", "[ANi] Hero - 01 [1080P][CHS].mkv", "magnet:?xt=urn:btih:1"),
                FeedEntry("2", "[ANi] Hero - 02 [1080P][CHS].mkv", "magnet:?xt=urn:btih:2"),
                FeedEntry("3", "[ANi] Other - 01 [1080P].mkv", "magnet:?xt=urn:btih:3"),
                FeedEntry("4", "Hero - 01-12", "magnet:?xt=urn:btih:4"),
            ]
        )
        provider = SimpleNamespace(search=AsyncMock(return_value=[candidate()]))
        container.automation_subscriptions._providers = {"bangumi": provider}
        payload = {"url": "https://example.org/rss?secret=private", "parser": "bangumi"}
        response = client.post("/api/v1/automation/feeds/analyze", json=payload)
        assert response.status_code == 200, response.text
        result = response.json()["data"]
        assert result["total_entries"] == 4
        assert result["unrecognized"] == 1
        assert len(result["candidates"]) == 2
        hero, other = result["candidates"]
        assert hero["entry_count"] == 2
        assert hero["rule"]["provider_id"] == "12"
        assert hero["rule"]["preferred_subtitle"] == "CHS"
        assert other["rule"]["title"] == "Other"
        assert other["rule"].get("provider_id") is None  # Fuzzy hit must not auto-bind.
        assert other["warning"]
        for endpoint in ("feeds", "subscriptions", "downloads", "releases"):
            assert client.get(f"/api/v1/automation/{endpoint}").json()["data"] == []

        confirmation = {"url": payload["url"], "rules": [hero["rule"]]}
        saved = client.post("/api/v1/automation/subscriptions/confirm", json=confirmation)
        assert saved.status_code == 200, saved.text
        data = saved.json()["data"]
        assert data["created"] == 1
        assert not data["automation_enabled"]
        assert "private" not in saved.text
        repeated = client.post("/api/v1/automation/subscriptions/confirm", json=confirmation)
        assert repeated.json()["data"]["created"] == 0
        assert len(client.get("/api/v1/automation/subscriptions").json()["data"]) == 1
        assert client.get("/api/v1/automation/downloads").json()["data"] == []


def test_invalid_confirmation_does_not_partially_save_source_or_rules(tmp_path: Path) -> None:
    with TestClient(create_app(app_settings(tmp_path))) as client:
        response = client.post(
            "/api/v1/automation/subscriptions/confirm",
            json={
                "url": "https://example.org/rss",
                "rules": [draft(), draft(poster_url="http://localhost/private")],
            },
        )
        assert response.status_code == 400
        assert client.get("/api/v1/automation/feeds").json()["data"] == []
        assert client.get("/api/v1/automation/subscriptions").json()["data"] == []


def test_parallel_confirmation_does_not_duplicate_rules(tmp_path: Path) -> None:
    with TestClient(create_app(app_settings(tmp_path))) as client:
        onboarding = client.app.state.container.automation_subscriptions
        with ThreadPoolExecutor(max_workers=2) as pool:
            calls = [
                pool.submit(onboarding.subscribe, "https://a.test/rss", "RSS", [draft()])
                for _ in range(2)
            ]
            results = [call.result() for call in calls]
        assert sorted(result["created"] for result in results) == [0, 1]
        assert len(client.get("/api/v1/automation/subscriptions").json()["data"]) == 1


def test_slow_metadata_returns_drafts_without_holding_request_open(tmp_path: Path) -> None:
    with TestClient(create_app(app_settings(tmp_path))) as client:
        container = client.app.state.container
        container.automation_service._rss.fetch = AsyncMock(
            return_value=[
                FeedEntry("1", "[ANi] Hero - 01 [1080P].mkv", "magnet:?xt=urn:btih:1"),
            ]
        )

        async def slow_search(*_args, **_kwargs):
            await asyncio.sleep(5)
            return [candidate()]

        container.automation_subscriptions.metadata_budget_seconds = 0.01
        container.automation_subscriptions._providers = {
            "bangumi": SimpleNamespace(search=slow_search)
        }
        response = client.post(
            "/api/v1/automation/feeds/analyze", json={"url": "https://a.test/rss"}
        )
        assert response.status_code == 200
        result = response.json()["data"]["candidates"][0]
        assert result["rule"]["title"] == "Hero"
        assert "超时" in result["warning"]


def test_metadata_failure_still_returns_editable_drafts_and_parser_skips_search(
    tmp_path: Path,
) -> None:
    with TestClient(create_app(app_settings(tmp_path))) as client:
        container = client.app.state.container
        container.automation_service._rss.fetch = AsyncMock(
            return_value=[
                FeedEntry("1", "[ANi] Hero - 01 [1080P].mkv", "magnet:?xt=urn:btih:1"),
            ]
        )
        provider = SimpleNamespace(search=AsyncMock(side_effect=RuntimeError("private-token")))
        container.automation_subscriptions._providers = {"bangumi": provider}
        response = client.post(
            "/api/v1/automation/feeds/analyze", json={"url": "https://a.test/rss"}
        )
        assert response.status_code == 200
        assert "private-token" not in response.text
        assert response.json()["data"]["candidates"][0]["warning"]
        provider.search.reset_mock()
        response = client.post(
            "/api/v1/automation/feeds/analyze",
            json={
                "url": "https://a.test/rss",
                "parser": "parser",
            },
        )
        assert response.status_code == 200
        provider.search.assert_not_called()
        unavailable = client.post("/api/v1/automation/metadata/search", json={"query": "Hero"})
        assert unavailable.status_code == 503
        assert "private-token" not in unavailable.text


def test_rule_edit_roundtrip_archive_language_and_offsets(tmp_path: Path) -> None:
    with TestClient(create_app(app_settings(tmp_path))) as client:
        saved = client.post(
            "/api/v1/automation/subscriptions/confirm",
            json={
                "url": "https://a.test/rss",
                "rules": [draft()],
            },
        ).json()["data"]
        rule = saved["rules"][0]
        update = {
            **rule,
            "year": 2026,
            "season": 1,
            "season_offset": 1,
            "episode_offset": -12,
            "preferred_subtitle": "CHS",
            "source_title": "Hero",
            "air_weekday": 0,
        }
        response = client.put(f"/api/v1/automation/subscriptions/{rule['id']}", json=update)
        assert response.status_code == 200, response.text
        assert response.json()["data"]["air_weekday"] == 0
        repo = client.app.state.container.automation_service._repo
        record = repo.get_subscription(rule["id"])
        release = "[ANi] Hero - 13 [1080P][CHS].mkv"
        assert match_subscription(analyze_release(release), record, release) is None
        traditional = release.replace("CHS", "CHT")
        assert (
            match_subscription(analyze_release(traditional), record, traditional)
            == "字幕语言与偏好不符"
        )
        invalid = client.put(
            f"/api/v1/automation/subscriptions/{rule['id']}", json={**update, "season_offset": -2}
        )
        assert invalid.status_code == 400
        assert repo.get_subscription(rule["id"]).options_json["season_offset"] == 1
        archived = client.put(
            f"/api/v1/automation/subscriptions/{rule['id']}", json={**update, "archived": True}
        )
        assert archived.status_code == 200
        assert (
            match_subscription(analyze_release(release), repo.get_subscription(rule["id"]), release)
            == "订阅已归档"
        )
        automation = client.app.state.container.automation_service
        automation._rss.fetch = AsyncMock(
            return_value=[
                FeedEntry("1", release, "magnet:?xt=urn:btih:1"),
                FeedEntry("2", traditional, "magnet:?xt=urn:btih:2"),
            ]
        )
        downloader = SimpleNamespace(
            by_tag=AsyncMock(side_effect=[[], [{"hash": "test", "progress": 0}]]),
            add=AsyncMock(return_value=True),
        )
        automation._qb = lambda: downloader
        client.put(
            "/api/v1/automation/settings",
            json={
                "enabled": True,
                "qb_url": "http://127.0.0.1:8080",
                "qb_username": "test",
                "qb_password": "test",
                "qb_save_root": "/downloads",
            },
        )
        refresh_url = f"/api/v1/automation/feeds/{saved['feed']['id']}/refresh"
        assert client.post(refresh_url).json()["data"]["submitted"] == 0
        downloader.add.assert_not_called()
        client.put(f"/api/v1/automation/subscriptions/{rule['id']}", json=update)
        assert client.post(refresh_url).json()["data"]["submitted"] == 1
        assert downloader.add.call_args.args[1] == "/downloads/Hero/Season 2"
        job = repo.list_downloads()[0]
        assert {k: job.naming_json[k] for k in ("title", "season", "episode")} == {
            "title": "Hero",
            "season": 2,
            "episode": 1,
        }


def test_download_uses_submission_snapshot_after_rule_is_edited(tmp_path: Path) -> None:
    settings = app_settings(tmp_path)
    with TestClient(create_app(settings)) as client:
        automation = client.app.state.container.automation_service
        fake = FakeQbittorrent(settings.media_root)
        automation._qb = lambda: fake
        automation._rss.fetch = AsyncMock(
            return_value=[
                FeedEntry("1", "[ANi] Hero - 01 [1080P].mkv", "magnet:?xt=urn:btih:1"),
            ]
        )
        saved = client.post(
            "/api/v1/automation/subscriptions/confirm",
            json={
                "url": "https://a.test/rss",
                "rules": [draft()],
            },
        ).json()["data"]
        client.put(
            "/api/v1/automation/settings",
            json={
                "enabled": True,
                "qb_url": "http://127.0.0.1:8080",
                "qb_username": "test",
                "qb_password": "test",
                "qb_save_root": "/downloads",
            },
        )
        assert (
            client.post(f"/api/v1/automation/feeds/{saved['feed']['id']}/refresh").json()["data"][
                "submitted"
            ]
            == 1
        )
        rule = saved["rules"][0]
        client.put(
            f"/api/v1/automation/subscriptions/{rule['id']}",
            json={
                **rule,
                "season_offset": 1,
                "episode_offset": 12,
                "title": "New name",
                "archived": True,
            },
        )
        client.post("/api/v1/automation/downloads/sync")
        assert client.get("/api/v1/automation/downloads").json()["data"][0]["state"] == "organized"
        assert (settings.media_root / "Hero/Season 1/Hero S01E01.mkv").is_file()


def test_additive_migration_keeps_existing_subscriptions(tmp_path: Path) -> None:
    settings = app_settings(tmp_path)
    with TestClient(create_app(settings)) as client:
        client.post(
            "/api/v1/automation/subscriptions/confirm",
            json={
                "url": "https://a.test/rss",
                "rules": [draft()],
            },
        )
        factory = client.app.state.container.automation_service._repo._factory
        with factory.kw["bind"].begin() as connection:
            connection.execute(
                text("ALTER TABLE automation_subscriptions DROP COLUMN options_json")
            )
            connection.execute(text("ALTER TABLE automation_downloads DROP COLUMN naming_json"))
        initialize_database(factory)
        initialize_database(factory)  # Startup upgrade is repeatable.
        rules = client.get("/api/v1/automation/subscriptions").json()["data"]
        assert len(rules) == 1
        assert rules[0]["title"] == "Hero"
        assert rules[0]["season_offset"] == 0
        assert rules[0]["archived"] is False


def test_posters_cache_remote_and_prefer_available_local_file(tmp_path: Path) -> None:
    settings = app_settings(tmp_path)
    buffer = BytesIO()
    Image.new("RGB", (500, 750), "purple").save(buffer, "JPEG")
    content = buffer.getvalue()
    with TestClient(create_app(settings)) as client:
        cache = client.app.state.container.subscription_artwork
        cache._downloader = SimpleNamespace(
            download=AsyncMock(return_value=RemoteArtwork(content, ".jpg"))
        )
        url = "https://lain.bgm.tv/pic/cover/l/test.jpg"

        async def concurrent() -> None:
            paths = await asyncio.gather(*(cache.get(url) for _ in range(5)))
            assert len(set(paths)) == 1
            assert paths[0].read_bytes() == content

        asyncio.run(concurrent())
        image = client.get("/api/v1/automation/poster", params={"url": url})
        assert image.status_code == 200
        assert image.headers["content-type"] == "image/webp"
        cache._downloader.download.assert_awaited_once()
        assert (
            client.get(
                "/api/v1/automation/poster", params={"url": "http://localhost/image"}
            ).status_code
            == 400
        )
        (settings.media_root / "Hero").mkdir()
        (settings.media_root / "Hero/poster.jpg").write_bytes(content)
        client.post(
            "/api/v1/automation/subscriptions/confirm",
            json={
                "url": "https://a.test/rss",
                "rules": [draft()],
            },
        )
        rule = client.get("/api/v1/automation/subscriptions").json()["data"][0]
        assert rule["local_poster_url"]
        local = client.get(rule["local_poster_url"])
        assert local.status_code == 200
        assert (
            client.get(
                rule["local_poster_url"], headers={"If-None-Match": local.headers["etag"]}
            ).status_code
            == 304
        )
