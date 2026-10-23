from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi.testclient import TestClient
from test_access_control import PASSWORD, setup
from test_automation import app_settings

from app.core.diagnostics import DiagnosticHandler, active_log_store
from app.infrastructure.persistence.error_logs import ErrorLogStore
from app.main import create_app

ENDPOINT = "/api/v1/system/error-logs"


def test_failed_rss_is_traceable_without_secrets_and_success_is_not_logged(tmp_path):
    settings = app_settings(tmp_path)
    app = create_app(settings)
    with TestClient(app) as client:
        secret = "https://user:password@rss.test/private-passkey?token=hidden-token"
        cause = httpx.ConnectError(secret)
        cause.__cause__ = ConnectionRefusedError(111, "password=secret")
        app.state.container.automation_service._rss.fetch = AsyncMock(side_effect=cause)
        result = client.post(
            "/api/v1/automation/feeds/analyze",
            json={
                "url": "https://rss.test/private-passkey?token=hidden-token",
                "parser": "parser",
            },
            headers={"X-Request-ID": "do-not-store-this-secret"},
        )
        assert result.status_code == 503
        assert result.json()["error"]["details"]["reason"] == "CONNECTION"
        request_id = result.json()["request_id"]
        assert request_id == result.headers["X-Request-ID"]
        assert request_id.startswith("req_")
        logs = client.get(ENDPOINT, params={"request_id": request_id}).json()["data"]
        (item,) = logs["items"]
        assert item["code"] == "RSS_UNAVAILABLE"
        assert item["level"] == "ERROR"
        assert [e["type"] for e in item["exceptions"]] == [
            "DomainError",
            "ConnectError",
            "ConnectionRefusedError",
        ]
        assert item["exceptions"][0]["frames"]
        assert item["route"] == "/api/v1/automation/feeds/analyze"
        app.state.container.automation_service._rss.fetch = AsyncMock(return_value=[])
        assert (
            client.post(
                "/api/v1/automation/feeds/analyze",
                json={"url": "https://rss.test/", "parser": "parser"},
            ).status_code
            == 200
        )
        assert len(client.get(ENDPOINT).json()["data"]["items"]) == 1
        assert client.get("/api/v1/system/health").status_code == 200
        raw = app.state.error_logs.path.read_bytes()
        for value in (
            "private-passkey",
            "hidden-token",
            "password=secret",
            "do-not-store-this-secret",
        ):
            assert value.encode() not in raw
            assert value not in json.dumps(logs)
    with TestClient(create_app(settings)) as restarted:
        assert restarted.get(ENDPOINT).json()["data"]["items"][0]["request_id"] == request_id


@pytest.mark.parametrize(
    ("error", "reason"),
    [
        (TimeoutError(), "TIMEOUT"),
        (httpx.ReadTimeout("secret"), "TIMEOUT"),
        (httpx.ProxyError("password=secret"), "PROXY"),
        (
            httpx.HTTPStatusError(
                "token=secret",
                request=httpx.Request("GET", "https://test/"),
                response=httpx.Response(403),
            ),
            "HTTP_STATUS",
        ),
        (ValueError("private XML content"), "INVALID_FEED"),
        (RuntimeError("secret"), "UNEXPECTED"),
    ],
)
def test_rss_error_classification(tmp_path, error, reason):
    with TestClient(create_app(app_settings(tmp_path))) as client:
        client.app.state.container.automation_service._rss.fetch = AsyncMock(side_effect=error)
        response = client.post(
            "/api/v1/automation/feeds/analyze", json={"url": "https://test/", "parser": "parser"}
        )
        assert response.status_code == 503
        assert response.json()["error"]["details"]["reason"] == reason
        assert "secret" not in response.text
        if reason == "HTTP_STATUS":
            assert response.json()["error"]["details"]["upstream_status"] == 403


def test_unhandled_exception_and_validation_no_duplicate_or_payload(tmp_path):
    app = create_app(app_settings(tmp_path))

    @app.get("/api/v1/test-error/{identity}")
    def broken(identity: str):
        raise RuntimeError("token-secret must not be persisted")

    with TestClient(app) as client:
        response = client.get("/api/v1/test-error/private-value?token=private-query")
        assert response.status_code == 500
        assert response.json()["error"]["code"] == "INTERNAL_ERROR"
        items = client.get(ENDPOINT).json()["data"]["items"]
        assert len(items) == 1
        assert items[0]["route"] == "/api/v1/test-error/{identity}"
        assert items[0]["exceptions"][0]["type"] == "RuntimeError"
        assert "token-secret" not in json.dumps(items)
        assert "private-value" not in json.dumps(items)
        assert "private-query" not in json.dumps(items)
        assert client.post("/api/v1/automation/feeds/analyze", json={"url": []}).status_code == 422
        assert client.get("/api/v1/unknown-secret").status_code == 404
        assert len(client.get(ENDPOINT).json()["data"]["items"]) == 2
        assert (
            client.get(ENDPOINT, params={"level": "WARNING"}).json()["data"]["items"][0]["status"]
            == 422
        )


def test_store_retention_pagination_and_concurrent_writes(tmp_path):
    store = ErrorLogStore(tmp_path, max_entries=3)
    for index in range(6):
        store.append({"level": "ERROR", "code": "TEST", "request_id": f"req_{index}"})
    first = store.list(limit=2)
    assert [i["request_id"] for i in first["items"]] == ["req_5", "req_4"]
    older = store.list(limit=2, before_id=first["next_before_id"])
    assert [i["request_id"] for i in older["items"]] == ["req_3"]
    assert older["next_before_id"] is None
    assert store.list(code="OTHER")["items"] == []
    assert store.list(request_id="req_5")["items"][0]["request_id"] == "req_5"

    async def concurrent():
        await asyncio.gather(
            *(asyncio.to_thread(store.append, {"level": "ERROR", "code": "TEST"}) for _ in range(8))
        )

    asyncio.run(concurrent())
    assert len(store.list()["items"]) == 3
    assert not store.write_failed


def test_logging_is_exception_only_context_isolated_and_handler_removed(tmp_path):
    app = create_app(app_settings(tmp_path))

    @app.get("/api/v1/test-log")
    def log():
        logger = logging.getLogger("app.test")
        logger.info("not persisted")
        try:
            raise ValueError("raw-secret-message")
        except ValueError:
            logger.warning("arbitrary secret %s", "raw-secret-argument")
        return {"ok": True}

    with TestClient(app) as client:
        client.get("/api/v1/test-log")
        rows = client.get(ENDPOINT).json()["data"]["items"]
        assert len(rows) == 1
        assert rows[0]["exceptions"][0]["type"] == "ValueError"
        assert "raw-secret" not in json.dumps(rows)
        unrelated_store = ErrorLogStore(tmp_path / "other")
        handler = DiagnosticHandler(unrelated_store)
        context = active_log_store.set(app.state.error_logs)
        try:
            handler.emit(logging.makeLogRecord({"name": "app.test", "msg": "secret"}))
        finally:
            active_log_store.reset(context)
        assert unrelated_store.list()["items"] == []
    assert not any(
        isinstance(h, DiagnosticHandler) and h.store is app.state.error_logs
        for h in logging.getLogger("app").handlers
    )


def test_store_failure_does_not_break_requests_and_queries_report_failure(tmp_path, monkeypatch):
    app = create_app(app_settings(tmp_path))
    with TestClient(app) as client:

        def unavailable():
            raise sqlite3.OperationalError("secret path")

        monkeypatch.setattr(app.state.error_logs, "_connect", unavailable)
        assert client.get("/api/v1/system/health").status_code == 200
        result = client.get(ENDPOINT)
        assert result.status_code == 503
        assert result.json()["error"]["code"] == "ERROR_LOG_UNAVAILABLE"
        assert "secret path" not in result.text
        assert app.state.error_logs.write_failed


def test_logs_require_admin_and_full_scope_when_auth_enabled(tmp_path):
    with TestClient(create_app(app_settings(tmp_path))) as client:
        setup(client)
        assert client.get(ENDPOINT).status_code == 200
        token = client.post("/api/v1/auth/tokens", json={"name": "read", "scope": "read"}).json()[
            "data"
        ]["token"]
        assert client.get(ENDPOINT, headers={"Authorization": "Bearer " + token}).status_code == 403
        client.post(
            "/api/v1/auth/users",
            json={"username": "viewer", "password": PASSWORD, "role": "viewer"},
        )
        client.cookies.clear()
        assert client.get(ENDPOINT).status_code == 401
        client.post("/api/v1/auth/login", json={"username": "viewer", "password": PASSWORD})
        assert client.get(ENDPOINT).status_code == 403
        assert client.get(ENDPOINT + "/").status_code in {401, 403}


def test_log_query_limits_are_validated(tmp_path):
    with TestClient(create_app(app_settings(tmp_path))) as client:
        for params in ({"limit": 201}, {"limit": 0}, {"before_id": -1}, {"level": "INFO"}):
            assert client.get(ENDPOINT, params=params).status_code == 422


def test_startup_failure_is_persisted_without_leaking_secrets(tmp_path, monkeypatch):
    import app.main as main_module

    settings = app_settings(tmp_path)

    def broken_container(_settings):
        raise RuntimeError("startup-secret")

    monkeypatch.setattr(main_module, "build_container", broken_container)
    with pytest.raises(RuntimeError), TestClient(create_app(settings)):
        pass
    rows = ErrorLogStore(settings.data_dir / "logs").list()["items"]
    assert len(rows) == 1
    assert rows[0]["exceptions"][0]["type"] == "RuntimeError"
    assert "startup-secret" not in json.dumps(rows)
