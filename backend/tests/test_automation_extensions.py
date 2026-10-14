from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from test_automation import app_settings

from app.domain.automation import analyze_release, match_subscription
from app.domain.automation_organizer import organize_plan
from app.infrastructure.automation.rss import FeedEntry
from app.main import create_app


def rule(client, **options):
    feed = client.post(
        "/api/v1/automation/feeds", json={"name": "Hero RSS", "url": "https://example.test/feed"}
    ).json()["data"]
    result = client.post(
        "/api/v1/automation/subscriptions",
        json={
            "feed_id": feed["id"],
            "title": "Hero",
            "folder_name": "Hero",
            "aliases": [],
            "season": 1,
            **options,
        },
    )
    assert result.status_code == 200, result.text
    client.put(
        "/api/v1/automation/settings",
        json={
            "qb_url": "http://localhost:8080",
            "qb_username": "admin",
            "qb_password": "test",
            "qb_save_root": "/downloads",
        },
    )
    return result.json()["data"]


class MultiQb:
    def __init__(self, root):
        self.root = root
        self.tasks = {}
        self.added = []
        self.actions = []
        self.renames = []

    def task(self, tag, path, names, version=1):
        directory = self.root / path.removeprefix("/downloads/")
        directory.mkdir(parents=True, exist_ok=True)
        for name in names:
            target = directory / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(f"version-{version}".encode())
        self.tasks[tag] = {
            "hash": tag,
            "names": names[:],
            "directory": directory,
            "progress": 1.0,
            "state": "uploading",
        }

    async def add(self, url, path, tag):
        version = int(url.rsplit(":", 1)[-1])
        self.added.append(tag)
        self.task(tag, path, [f"[ANi] Hero - 01v{version} [1080p].mkv"], version)
        return True

    async def by_tag(self, tag):
        return [self.tasks[tag]] if tag in self.tasks else []

    async def files(self, task_hash):
        return [{"name": n} for n in self.tasks[task_hash]["names"]]

    async def rename_file(self, task_hash, source, target):
        self.renames.append((task_hash, source, target))
        task = self.tasks[task_hash]
        target_path = task["directory"] / target
        target_path.parent.mkdir(parents=True, exist_ok=True)
        assert not target_path.exists(), "a rename attempted to overwrite a file"
        (task["directory"] / source).rename(target_path)
        task["names"][task["names"].index(source)] = target

    async def action(self, task_hash, action):
        self.actions.append((task_hash, action))
        if action == "remove":
            self.tasks.pop(task_hash)


def release(service, rule_id, version=1, title=None):
    row = service._repo.get_subscription(rule_id)
    title = title or f"[ANi] Hero - 01v{version} [1080p]"
    return service._repo.get_or_add_release(
        row.feed_id,
        f"v{version}:{title}",
        {
            "title": title,
            "download_url": f"magnet:?xt=urn:btih:{version}",
            "parsed": analyze_release(title).json(),
        },
    )


def test_search_cache_pt_credentials_and_single_download_requires_confirmation(
    tmp_path, monkeypatch
):
    from app.infrastructure.automation.rss import HttpRssClient

    fetch = AsyncMock(
        return_value=[FeedEntry("one", "[ANi] Hero - 01 [1080p]", "magnet:?xt=urn:btih:1")]
    )
    monkeypatch.setattr(HttpRssClient, "fetch", fetch)
    with TestClient(create_app(app_settings(tmp_path))) as client:
        rid = rule(client)["id"]
        container = client.app.state.container
        qb = MultiQb(container.settings.media_root)
        container.automation_service._qb = lambda: qb
        response = client.put(
            "/api/v1/automation/features/settings",
            json={
                "sources": [
                    {
                        "id": "pt",
                        "name": "PT",
                        "kind": "torznab",
                        "url": "https://pt.test/api",
                        "api_key": "private-secret",
                    }
                ]
            },
        )
        assert response.status_code == 200
        assert "private-secret" not in response.text
        assert fetch.await_count == 0
        assert client.get("/api/v1/automation/search").json()["data"]["items"] == []
        result = client.post(
            "/api/v1/automation/search", json={"source_id": "pt", "query": "Hero & Friends"}
        )
        assert result.status_code == 200, result.text
        assert "apikey=private-secret" in fetch.call_args.args[0]
        assert "Hero+%26+Friends" in fetch.call_args.args[0]
        item = result.json()["data"]["items"][0]
        assert "private-secret" not in result.text
        assert client.get("/api/v1/automation/search").json()["data"] == result.json()["data"]
        assert fetch.await_count == 1
        path = f"/api/v1/automation/releases/{item['id']}/download"
        assert client.post(path, json={"subscription_id": rid}).status_code == 200
        assert qb.added == []
        payload = {"subscription_id": rid, "confirm": True}
        assert client.post(path, json=payload).json()["data"]["confirmed"] is True
        assert client.post(path, json=payload).status_code == 200
        assert len(qb.added) == 1


def test_backfill_skips_existing_local_and_queued_and_revalidates(tmp_path):
    with TestClient(create_app(app_settings(tmp_path))) as client:
        rid = rule(client, expected_episodes=3)["id"]
        service = client.app.state.container.automation_service
        directory = service._media_root / "Hero" / "Season 1"
        directory.mkdir(parents=True)
        (directory / "Hero S01E01.mkv").write_bytes(b"local")
        second = release(service, rid, title="[ANi] Hero - 02 [1080p]")
        third = release(service, rid, title="[ANi] Hero - 03 [1080p]")
        service._repo.create_download(second.id, rid, "/downloads", str(directory), {"episode": 2})
        path = f"/api/v1/automation/subscriptions/{rid}/backfill"
        data = client.get(path).json()["data"]
        assert data["local"] == [1]
        assert data["queued"] == [2]
        assert data["missing"] == [
            {
                "episode": 3,
                "candidate": {"release_id": third.id, "title": third.title, "version": None},
            }
        ]
        (directory / "Hero S01E03.mkv").write_bytes(b"arrived")
        assert (
            client.post(path, json={"release_ids": [third.id], "confirm": True}).status_code == 409
        )


def test_movie_special_batch_policy_and_nested_file_plan():
    from types import SimpleNamespace

    sample = "[ANi] Hero Movie (2026) [1080p]"
    r = SimpleNamespace(
        title="Hero Movie",
        aliases=[],
        season=0,
        episode_offset=0,
        preferred_group=None,
        preferred_resolution=None,
        exclude_keywords=[],
        options_json={"content_kind": "movie"},
    )
    assert match_subscription(analyze_release(sample), r, sample) is None
    r.options_json = {"content_kind": "series"}
    assert match_subscription(analyze_release(sample), r, sample) is not None
    plan = organize_plan(
        [
            {"name": n}
            for n in [
                "Main/Hero - 13.mkv",
                "Main/Hero - 14.mkv",
                "Sub/Hero - 13.chs.ass",
                "Sub/Hero - 13.cht.ass",
                "NCOP/Hero NCOP01.mkv",
            ]
        ],
        {"title": "Hero", "season": 2, "episode_offset": -12, "allow_batch": True},
    )
    assert {p["target"] for p in plan} == {
        "Hero S02E01.mkv",
        "Hero S02E02.mkv",
        "Hero S02E01.sc.ass",
        "Hero S02E01.tc.ass",
    }
    with pytest.raises(ValueError):
        organize_plan([{"name": "../escape.mkv"}], {"title": "Hero", "season": 1, "episode": 1})
    with pytest.raises(ValueError):
        organize_plan(
            [{"name": "a/Hero - 01.mkv"}, {"name": "b/Hero - 01.mkv"}],
            {"title": "Hero", "season": 1},
        )


def test_revision_download_promote_restore_and_next_revision(tmp_path):
    with TestClient(create_app(app_settings(tmp_path))) as client:
        rid = rule(client)["id"]
        service = client.app.state.container.automation_service
        qb = MultiQb(service._media_root)
        service._qb = lambda: qb
        jobs = []
        for version in (1, 2, 3):
            candidate = release(service, rid, version)
            result = client.post(
                f"/api/v1/automation/releases/{candidate.id}/download",
                json={"subscription_id": rid, "confirm": True},
            )
            assert result.status_code == 200, result.text
            assert result.json()["data"]["confirmed"] is True
            assert client.post("/api/v1/automation/downloads/sync").status_code == 200
            job = service._repo.get_download_by_release(candidate.id)
            if version > 1:
                assert job.state == "revision_ready", job.error
                url = f"/api/v1/automation/downloads/{job.id}/revision"
                payload = {"previous_id": jobs[-1].id, "confirm": True}
                preview = client.post(url, json={**payload, "confirm": False})
                assert preview.status_code == 200, preview.text
                actual = service._media_root / "Hero" / "Season 1" / "Hero S01E01.mkv"
                assert actual.read_bytes() == f"version-{version - 1}".encode()
                promote = client.post(url, json=payload)
                assert promote.status_code == 200, promote.text
                assert actual.read_bytes() == f"version-{version}".encode()
                assert client.post(url, json=payload).status_code == 200  # resumable/idempotent
                if version == 2:
                    restored = client.post(url + "/restore", json=payload)
                    assert restored.status_code == 200, restored.text
                    assert actual.read_bytes() == b"version-1"
                    assert client.post(url, json=payload).status_code == 200
            jobs.append(job)
        assert (
            client.post(
                f"/api/v1/automation/downloads/{jobs[1].id}/revision/restore",
                json={"previous_id": jobs[0].id, "confirm": True},
            ).status_code
            == 409
        )


def test_managed_task_remove_never_deletes_files_and_restore_conflict_is_rejected(tmp_path):
    with TestClient(create_app(app_settings(tmp_path))) as client:
        rid = rule(client)["id"]
        service = client.app.state.container.automation_service
        qb = MultiQb(service._media_root)
        service._qb = lambda: qb
        candidate = release(service, rid)
        client.post(
            f"/api/v1/automation/releases/{candidate.id}/download",
            json={"subscription_id": rid, "confirm": True},
        )
        client.post("/api/v1/automation/downloads/sync")
        job = service._repo.list_downloads()[0]
        original = Path(job.local_path) / "[ANi] Hero - 01v1 [1080p].mkv"
        original.write_bytes(b"unrelated")
        url = f"/api/v1/automation/downloads/{job.id}/action"
        assert client.post(url, json={"action": "restore", "confirm": True}).status_code == 409
        assert original.read_bytes() == b"unrelated"
        assert client.post(url, json={"action": "remove"}).status_code == 400
        assert client.post(url, json={"action": "remove", "confirm": True}).status_code == 200
        assert (Path(job.local_path) / "Hero S01E01.mkv").exists()


def test_aria2_hardlink_publishes_without_renaming_or_showing_source(tmp_path):
    with TestClient(create_app(app_settings(tmp_path))) as client:
        rid = rule(client, downloader="aria2")["id"]
        service = client.app.state.container.automation_service
        service.features.save(
            {"aria2_url": "http://localhost:6800/jsonrpc", "aria2_save_root": "/downloads"}
        )
        candidate = release(service, rid)
        fake = MultiQb(service._media_root)
        service.downloader = lambda *args, **kwargs: fake
        response = client.post(
            f"/api/v1/automation/releases/{candidate.id}/download",
            json={"subscription_id": rid, "confirm": True},
        )
        assert response.status_code == 200, response.text
        client.post("/api/v1/automation/downloads/sync")
        job = service._repo.list_downloads()[0]
        assert job.state == "organized", job.error
        target = Path(job.local_path) / "Hero S01E01.mkv"
        source = Path(job.naming_json["source_local_path"]) / fake.tasks[job.qb_tag]["names"][0]
        assert target.samefile(source)
        assert not fake.renames
        assert source.parent.parent.name == ".cymediaflow-downloads"


def test_manual_exclusion_survives_feed_refresh(tmp_path):
    with TestClient(create_app(app_settings(tmp_path))) as client:
        rid = rule(client)["id"]
        service = client.app.state.container.automation_service
        candidate = release(service, rid)
        client.post(f"/api/v1/automation/releases/{candidate.id}/skip")
        service._rss.fetch = AsyncMock(
            return_value=[FeedEntry(candidate.identity, candidate.title, candidate.download_url)]
        )
        result = asyncio.run(service.refresh_feed(candidate.feed_id))
        assert result["submitted"] == 0
        assert service._repo.get_release(candidate.id).decision == "excluded"
