from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
from unittest.mock import AsyncMock

import httpx
from fastapi.testclient import TestClient
from test_automation import app_settings
from test_automation_extensions import rule

from app.infrastructure.automation.aria2 import Aria2Client
from app.main import create_app


def test_aria_rpc_secret_upload_stable_gid_and_magnet_metadata_followup(monkeypatch):
    from app.infrastructure.automation import aria2 as module

    monkeypatch.setattr(module, "fetch_torrent", AsyncMock(return_value=b"d4:infodee"))
    requests = []
    client = Aria2Client("http://localhost:6800/jsonrpc", "rpc-secret")
    gid = client.gid("cymf-1")

    async def rpc(method, *params):
        requests.append((method, params))
        if method == "tellActive":
            return [{"gid": gid, "followedBy": ["second-gid"]}]
        if method == "tellWaiting":
            return [
                {
                    "gid": "second-gid",
                    "status": "active",
                    "totalLength": "100",
                    "completedLength": "25",
                }
            ]
        if method == "tellStopped":
            return []
        return gid

    client.rpc = rpc
    assert asyncio.run(client.add("https://test/a.torrent", "/downloads", "cymf-1"))
    assert requests[0][0] == "addTorrent"
    assert base64.b64decode(requests[0][1][0]) == b"d4:infodee"
    assert requests[0][1][2]["gid"] == gid
    assert requests[0][1][2]["allow-overwrite"] == "false"
    assert asyncio.run(client.by_tag("cymf-1"))[0]["progress"] == 0.25


def mock_http(monkeypatch, handler):
    original = httpx.AsyncClient

    def factory(**kwargs):
        kwargs.pop("proxy", None)
        kwargs["transport"] = httpx.MockTransport(handler)
        return original(**kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", factory)


def test_calendar_notifications_webhook_signature_and_retry_state(tmp_path, monkeypatch):
    sent = []

    def handler(request):
        if request.url.path == "/calendar":
            return httpx.Response(
                200, json=[{"weekday": {"id": 3}, "items": [{"id": 123, "air_date": "2026-10-01"}]}]
            )
        sent.append(request)
        return httpx.Response(200)

    with TestClient(create_app(app_settings(tmp_path))) as client:
        rule(client, provider="bangumi", provider_id="123")
        mock_http(monkeypatch, handler)
        container = client.app.state.container
        assert (
            client.get("/api/v1/automation/calendar").json()["data"]["items"][0]["air_weekday"]
            is None
        )
        calendar = client.post("/api/v1/automation/calendar/refresh")
        assert calendar.status_code == 200, calendar.text
        assert calendar.json()["data"]["items"][0]["air_weekday"] == 2
        service = container.automation_updates
        container.automation_features.save(
            {
                "webhook_enabled": True,
                "webhook_url": "https://notify.test/hook",
                "webhook_secret": "signing-key",
                "webhook_events": ["organized"],
            }
        )
        asyncio.run(service.tick())
        container.automation_service._repo.add_event("organized", "Hero 已整理")
        asyncio.run(service.tick())
        assert len(sent) == 1
        assert (
            sent[0].headers["X-CyMediaFlow-Signature"]
            == "sha256=" + hmac.new(b"signing-key", sent[0].content, hashlib.sha256).hexdigest()
        )
        asyncio.run(service.tick())
        assert len(sent) == 1
        inbox = client.get("/api/v1/automation/notifications").json()["data"]
        assert inbox["unread"] == 1
        client.post(
            "/api/v1/automation/notifications/read", json={"through": inbox["items"][0]["id"]}
        )
        assert client.get("/api/v1/automation/notifications").json()["data"]["unread"] == 0


def test_llm_is_explicit_cached_and_never_submits_a_task(tmp_path, monkeypatch):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": '{"title":"Hero","episode":1,"season":1}'}}]},
        )

    with TestClient(create_app(app_settings(tmp_path))) as client:
        mock_http(monkeypatch, handler)
        assert (
            client.post(
                "/api/v1/automation/parser/suggest", json={"title": "ambiguous"}
            ).status_code
            == 400
        )
        saved = client.put(
            "/api/v1/automation/features/settings",
            json={
                "llm_enabled": True,
                "llm_url": "https://model.test/v1",
                "llm_model": "test-model",
                "llm_api_key": "never-return-me",
            },
        )
        assert "never-return-me" not in saved.text
        assert not calls
        result = client.post("/api/v1/automation/parser/suggest", json={"title": "ambiguous"})
        assert result.status_code == 200, result.text
        assert result.json()["data"]["requires_review"] is True
        cached = client.post("/api/v1/automation/parser/suggest", json={"title": "ambiguous"})
        assert cached.json()["data"]["cached"] is True
        assert len(calls) == 1
        assert not client.app.state.container.automation_service._repo.list_downloads()


def test_version_check_uses_saved_proxy_and_caches_without_updating(tmp_path, monkeypatch):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={"sha": "abcdef123456"})

    with TestClient(create_app(app_settings(tmp_path))) as client:
        mock_http(monkeypatch, handler)
        assert client.get("/api/v1/automation/version").json()["data"]["latest"] is None
        assert not calls
        response = client.post("/api/v1/automation/version/check")
        assert response.status_code == 200
        assert response.json()["data"]["latest"] == "abcdef123456"
        assert client.get("/api/v1/automation/version").json()["data"]["latest"] == "abcdef123456"
        assert len(calls) == 1
