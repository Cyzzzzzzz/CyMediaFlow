from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient
from sqlalchemy import inspect
from test_automation import app_settings
from test_automation_extensions import MultiQb, release, rule

from app.api.v1.automation_features import stream
from app.infrastructure.persistence.database import (
    AccessCredentialRecord,
    FeatureDocumentRecord,
    PasskeyRecord,
    UserRecord,
    initialize_database,
)
from app.main import create_app


def test_additive_upgrade_preserves_existing_rules_tasks_and_opt_in(tmp_path):
    settings = app_settings(tmp_path)
    with TestClient(create_app(settings)) as client:
        rid = rule(client, episode_offset=-12)["id"]
        c = client.app.state.container
        item = release(c.automation_service, rid)
        job = c.automation_service._repo.create_download(item.id, rid, "/downloads", "/media", {})
        factory = c.session_factory
        engine = factory.kw["bind"]
        # Simulate the pre-P1 schema: only the new, empty tables are absent.
        for model in (PasskeyRecord, AccessCredentialRecord, UserRecord, FeatureDocumentRecord):
            model.__table__.drop(engine)
        initialize_database(factory)
        initialize_database(factory)
        assert "users" in inspect(engine).get_table_names()
        assert not c.access.enabled()
        assert c.automation_service._repo.get_subscription(rid).episode_offset == -12
        assert c.automation_service._repo.get_download(job.id).naming_json == {}
        assert not c.automation_service.get_config().enabled


def test_explicit_download_offset_special_preview_and_retry_when_auto_disabled(tmp_path):
    with TestClient(create_app(app_settings(tmp_path))) as client:
        rid = rule(client, episode_offset=-12)["id"]
        s = client.app.state.container.automation_service
        item = release(s, rid, title="[ANi] Hero - 13 [1080p]")
        fake = MultiQb(s._media_root)
        original_add = fake.add
        fake.add = AsyncMock(side_effect=ValueError("offline"))
        s._qb = lambda: fake
        url = f"/api/v1/automation/releases/{item.id}/download"
        response = client.post(url, json={"subscription_id": rid, "episode": 1, "confirm": True})
        assert response.json()["data"]["episode"] == 1
        job = s._repo.get_download_by_release(item.id)
        assert job.naming_json["episode"] == 1
        s._repo.update_download(job.id, state="retry")
        fake.add = original_add
        result = client.post(f"/api/v1/automation/downloads/{job.id}/retry")
        assert result.status_code == 200, result.text
        assert result.json()["data"]["confirmed"]
        assert not s.get_config().enabled
        assert (
            client.post(
                f"/api/v1/automation/downloads/{job.id}/action", json={"action": "organize"}
            ).status_code
            == 400
        )
        special = release(s, rid, title="[ANi] Hero SP01 [1080p]")
        preview = client.post(
            f"/api/v1/automation/releases/{special.id}/download",
            json={"subscription_id": rid, "episode": 1},
        )
        assert preview.json()["data"]["season"] == 0


def test_excluded_releases_are_not_offered_for_backfill(tmp_path):
    with TestClient(create_app(app_settings(tmp_path))) as client:
        rid = rule(client, expected_episodes=1)["id"]
        s = client.app.state.container.automation_service
        item = release(s, rid)
        client.post(f"/api/v1/automation/releases/{item.id}/skip")
        result = client.get(f"/api/v1/automation/subscriptions/{rid}/backfill")
        assert result.json()["data"]["missing"] == [{"episode": 1, "candidate": None}]


def test_sse_resumes_after_last_event_without_replaying_old_entries(tmp_path):
    async def check(container):
        repo = container.automation_service._repo
        repo.add_event("review", "first")
        previous = repo.list_events(1)[0].id
        repo.add_event("organized", "second")
        request = SimpleNamespace(
            headers={"Last-Event-ID": str(previous)},
            app=SimpleNamespace(state=SimpleNamespace(container=container)),
            is_disconnected=AsyncMock(return_value=False),
        )
        response = await stream(request, after=0)
        iterator = response.body_iterator
        data = await iterator.__anext__()
        assert "second" in data and "first" not in data
        assert "event: update" in data
        assert response.headers["x-accel-buffering"] == "no"
        await iterator.aclose()

    with TestClient(create_app(app_settings(tmp_path))) as client:
        asyncio.run(check(client.app.state.container))
