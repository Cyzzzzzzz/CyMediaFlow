from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from test_automation import app_settings
from test_automation_extensions import MultiQb

from app.domain.automation import analyze_release, match_subscription
from app.domain.automation_organizer import organize_plan
from app.infrastructure.automation.rss import FeedEntry, parse_feed
from app.main import create_app

MIKAN_TITLE = (
    "电驭叛客：边缘行者 2「サイバーパンク：エッジランナーズ２」"
    "Cyberpunk Edgerunners S02E01~10 1080p 日英双语-多国字幕"
)


def analyze(client, titles, parser="parser"):
    service = client.app.state.container.automation_service
    service._rss.fetch = AsyncMock(
        return_value=[
            FeedEntry(str(i), title, f"magnet:?xt=urn:btih:{i}") for i, title in enumerate(titles)
        ]
    )
    response = client.post(
        "/api/v1/automation/feeds/analyze",
        json={"url": "https://example.test/batch-rss", "parser": parser},
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


@pytest.mark.parametrize(
    ("title", "season", "last"),
    [
        (MIKAN_TITLE, 2, 10),
        ("[ANi] Hero S02E01-E10 [1080p]", 2, 10),
        ("[ANi] Hero S02E01～10 [1080p]", 2, 10),
        ("[ANi] Hero [01~12] [1080p]", None, 12),
        ("Hero [01-12]", None, 12),
    ],
)
def test_batch_analysis_retains_both_ends(title, season, last):
    parsed = analyze_release(title)
    assert parsed.season == season
    assert parsed.episode == 1
    assert parsed.episode_end == last
    assert parsed.json()["episode_end"] == last
    assert "MULTI_EPISODE_RELEASE" in parsed.warnings
    assert parsed.group != "01-12"


def test_mikan_batch_draft_is_read_only_and_confirmation_preserves_permission(tmp_path):
    xml = (
        f"<rss><channel><item><title>{MIKAN_TITLE}</title>"
        '<enclosure url="https://example.test/batch.torrent" /></item></channel></rss>'
    ).encode()
    entries = parse_feed(xml, "https://example.test/rss")
    assert entries[0].title == MIKAN_TITLE
    with TestClient(create_app(app_settings(tmp_path))) as client:
        service = client.app.state.container.automation_service
        result = analyze(client, [entries[0].title])
        assert (result["total_entries"], result["unrecognized"]) == (1, 0)
        (candidate,) = result["candidates"]
        assert candidate["batch_count"] == 1
        assert candidate["episode_ranges"] == [{"season": 2, "start": 1, "end": 10}]
        assert candidate["rule"]["allow_batch"] is True
        assert candidate["rule"]["season"] == 2
        assert candidate["rule"].get("expected_episodes") is None
        for endpoint in ("feeds", "subscriptions", "downloads", "releases"):
            assert client.get(f"/api/v1/automation/{endpoint}").json()["data"] == []

        rule = {**candidate["rule"], "title": "赛博朋克：边缘行者", "folder_name": "Cyberpunk"}
        response = client.post(
            "/api/v1/automation/subscriptions/confirm",
            json={"url": "https://example.test/batch-rss", "rules": [rule]},
        )
        assert response.status_code == 200, response.text
        saved = response.json()["data"]["rules"][0]
        assert saved["allow_batch"] is True
        assert saved["season"] == 2
        assert saved["expected_episodes"] is None
        record = service._repo.get_subscription(saved["id"])
        assert match_subscription(analyze_release(MIKAN_TITLE), record, MIKAN_TITLE) is None
        assert service._repo.list_downloads() == []


@pytest.mark.parametrize("batch_first", [True, False])
def test_mixed_single_and_batch_keep_one_rule_without_changing_saved_options(tmp_path, batch_first):
    with TestClient(create_app(app_settings(tmp_path))) as client:
        single = "[ANi] Hero S02E01 [1080p]"
        batch = "[ANi] Hero S02E01~10 [1080p]"
        original = analyze(client, [single])["candidates"][0]["rule"]
        assert original["allow_batch"] is False
        saved = client.post(
            "/api/v1/automation/subscriptions/confirm",
            json={"url": "https://example.test/batch-rss", "rules": [original]},
        )
        assert saved.status_code == 200
        result = analyze(client, [batch, single] if batch_first else [single, batch])
        (candidate,) = result["candidates"]
        assert candidate["entry_count"] == 2
        assert candidate["batch_count"] == 1
        assert candidate["rule"]["allow_batch"] is True
        assert (
            client.get("/api/v1/automation/subscriptions").json()["data"][0]["allow_batch"] is False
        )


@pytest.mark.parametrize(
    "title",
    [
        "Hero S02E10~01 1080p",
        "Hero S02E01~1000 1080p",
        "Hero S01E01-S02E10 1080p",
        "Hero Complete Batch 1080p",
    ],
)
def test_ambiguous_invalid_or_cross_season_batches_are_not_auto_subscribed(tmp_path, title):
    with TestClient(create_app(app_settings(tmp_path))) as client:
        result = analyze(client, [title])
        assert result["candidates"] == []
        assert result["unrecognized"] == 1


class BatchQb(MultiQb):
    async def add(self, url, path, tag):
        self.added.append(tag)
        self.task(tag, path, [f"Cyberpunk Edgerunners S02E{i:02d}.mkv" for i in range(1, 11)])
        return True


@pytest.mark.parametrize("allowed", [True, False])
def test_batch_refresh_submits_once_and_organizes_each_episode_only_when_allowed(tmp_path, allowed):
    with TestClient(create_app(app_settings(tmp_path))) as client:
        service = client.app.state.container.automation_service
        qb = BatchQb(service._media_root)
        service._qb = lambda: qb
        draft = analyze(client, [MIKAN_TITLE])["candidates"][0]["rule"]
        draft.update(title="Cyberpunk", folder_name="Cyberpunk", allow_batch=allowed)
        response = client.post(
            "/api/v1/automation/subscriptions/confirm",
            json={"url": "https://example.test/batch-rss", "rules": [draft]},
        )
        assert response.status_code == 200, response.text
        saved = response.json()["data"]
        config = client.put(
            "/api/v1/automation/settings",
            json={
                "enabled": True,
                "qb_url": "http://localhost:8080",
                "qb_save_root": "/downloads",
                "qb_username": "test",
                "qb_password": "test",
            },
        )
        assert config.status_code == 200, config.text
        # Old cached release analysis must also be upgraded by an explicit refresh.
        legacy = analyze_release(MIKAN_TITLE).json()
        legacy.pop("episode_end")
        release = service._repo.get_or_add_release(
            saved["feed"]["id"],
            "0",
            {"title": MIKAN_TITLE, "download_url": "magnet:?xt=urn:btih:0", "parsed": legacy},
        )
        for _ in range(2):
            refreshed = client.post(f"/api/v1/automation/feeds/{saved['feed']['id']}/refresh")
            assert refreshed.status_code == 200, refreshed.text
        assert service._repo.get_release(release.id).parsed["episode_end"] == 10
        preview = client.post(
            f"/api/v1/automation/releases/{release.id}/download",
            json={"subscription_id": saved["rules"][0]["id"], "confirm": False},
        )
        if not allowed:
            assert service._repo.list_downloads() == []
            assert qb.added == []
            assert preview.status_code == 400
            assert "允许合集" in preview.text
            return
        assert preview.status_code == 200, preview.text
        assert preview.json()["data"]["episode"] is None
        (job,) = service._repo.list_downloads()
        assert len(qb.added) == 1
        assert job.naming_json["is_batch"] is True
        assert job.naming_json["episode"] is None
        assert job.naming_json["season"] == 2
        assert client.post("/api/v1/automation/downloads/sync").status_code == 200
        assert service._repo.get_download(job.id).state == "organized"
        assert {path.name for path in Path(job.local_path).glob("*.mkv")} == {
            f"Cyberpunk S02E{i:02d}.mkv" for i in range(1, 11)
        }


def test_single_remaining_file_in_batch_uses_its_own_number_and_offset():
    naming = {
        "title": "Hero",
        "season": 2,
        "episode": None,
        "is_batch": True,
        "episode_offset": -12,
    }
    plan = organize_plan([{"name": "Hero - 15.mkv"}], naming)
    assert plan[0]["target"] == "Hero S02E03.mkv"
    with pytest.raises(ValueError, match="缺少集号"):
        organize_plan([{"name": "Hero.mkv"}], naming)
    with pytest.raises(ValueError, match="单个视频包含多集"):
        organize_plan([{"name": "Hero S02E13~24.mkv"}], naming)


def test_cross_season_files_require_explicit_file_mapping():
    with pytest.raises(ValueError, match="多个季度"):
        organize_plan(
            [{"name": "Hero S01E01.mkv"}, {"name": "Hero S02E02.mkv"}],
            {"title": "Hero", "season": 2, "episode": None, "is_batch": True},
        )
