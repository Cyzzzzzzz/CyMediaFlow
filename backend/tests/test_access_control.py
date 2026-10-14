from __future__ import annotations

import base64
from datetime import timedelta
from types import SimpleNamespace

from fastapi.testclient import TestClient
from test_automation import app_settings

from app.application.access_service import utc_now
from app.infrastructure.persistence.database import AccessCredentialRecord
from app.main import create_app

PASSWORD = "long-test-password-123"


def setup(client):
    response = client.post("/api/v1/auth/setup", json={"username": "admin", "password": PASSWORD})
    assert response.status_code == 200, response.text
    assert "HttpOnly" in response.headers["set-cookie"]
    assert "SameSite=strict" in response.headers["set-cookie"]
    return response.json()["data"]


def test_opt_in_auth_healthcheck_roles_session_revocation_and_csrf(tmp_path):
    with TestClient(create_app(app_settings(tmp_path))) as client:
        assert client.get("/api/v1/automation/feeds").status_code == 200
        admin = setup(client)
        cookie = client.cookies["cymf_session"]
        assert (
            client.post(
                "/api/v1/auth/setup", json={"username": "other", "password": PASSWORD}
            ).status_code
            == 409
        )
        assert (
            client.post(
                "/api/v1/automation/run", headers={"Origin": "https://evil.test"}
            ).status_code
            == 403
        )
        viewer = client.post(
            "/api/v1/auth/users",
            json={"username": "reader", "password": PASSWORD, "role": "viewer"},
        ).json()["data"]
        client.cookies.clear()
        assert client.get("/api/v1/system/health").status_code == 200
        assert client.get("/api/v1/automation/feeds").status_code == 401
        assert (
            client.post(
                "/api/v1/auth/login", json={"username": "reader", "password": "incorrect"}
            ).status_code
            == 401
        )
        assert (
            client.post(
                "/api/v1/auth/login", json={"username": "reader", "password": PASSWORD}
            ).status_code
            == 200
        )
        viewer_cookie = client.cookies["cymf_session"]
        assert client.get("/api/v1/automation/feeds").status_code == 200
        assert (
            client.post(
                "/api/v1/automation/feeds", json={"name": "x", "url": "https://test/feed"}
            ).status_code
            == 403
        )
        assert client.get("/api/v1/auth/users").status_code == 403
        assert client.put("/api/v1/automation/features/settings", json={}).status_code == 403
        assert (
            client.post("/api/v1/auth/tokens", json={"name": "bad", "scope": "all"}).status_code
            == 403
        )
        assert (
            client.post("/api/v1/auth/tokens", json={"name": "read", "scope": "read"}).status_code
            == 200
        )
        client.cookies.set("cymf_session", cookie)
        assert (
            client.put(
                f"/api/v1/auth/users/{admin['id']}", json={"enabled": False, "role": "admin"}
            ).status_code
            == 400
        )
        assert (
            client.put(
                f"/api/v1/auth/users/{viewer['id']}", json={"enabled": False, "role": "viewer"}
            ).status_code
            == 200
        )
        assert client.app.state.container.access.authenticate(viewer_cookie) is None
        assert client.post("/api/v1/auth/logout").status_code == 200
        assert client.app.state.container.access.authenticate(cookie) is None


def test_scoped_tokens_mcp_and_expiry(tmp_path):
    with TestClient(create_app(app_settings(tmp_path))) as client:
        setup(client)
        issue = client.post("/api/v1/auth/tokens", json={"name": "MCP", "scope": "read", "days": 1})
        token = issue.json()["data"]["token"]
        token_id = issue.json()["data"]["id"]
        assert token not in client.get("/api/v1/auth/tokens").text
        headers = {"Authorization": "Bearer " + token}
        init = client.post("/api/v1/mcp", headers=headers, json={"id": 1, "method": "initialize"})
        assert init.json()["result"]["protocolVersion"] == "2025-06-18"
        result = client.post(
            "/api/v1/mcp",
            headers=headers,
            json={"id": 2, "method": "tools/call", "params": {"name": "list_subscriptions"}},
        )
        assert result.json()["result"]["content"][0]["type"] == "text"
        denied = client.post(
            "/api/v1/mcp",
            headers=headers,
            json={
                "id": 3,
                "method": "tools/call",
                "params": {"name": "refresh_feed", "arguments": {"feed_id": 1}},
            },
        )
        assert "error" in denied.json()
        assert (
            client.post("/api/v1/auth/passkeys/register/options", headers=headers).status_code
            == 403
        )
        assert client.get("/api/v1/auth/tokens", headers=headers).status_code == 403
        assert client.post("/api/v1/automation/downloads/sync", headers=headers).status_code == 403
        assert client.get("/api/v1/automation/downloads", headers=headers).status_code == 200
        with client.app.state.container.session_factory() as session:
            row = session.get(AccessCredentialRecord, token_id)
            row.expires_at = utc_now() - timedelta(seconds=1)
            session.commit()
        assert client.get("/api/v1/automation/downloads", headers=headers).status_code == 401


def test_passkey_registration_authentication_and_consumed_challenge(tmp_path, monkeypatch):
    import webauthn

    with TestClient(create_app(app_settings(tmp_path))) as client:
        setup(client)
        assert (
            client.put(
                "/api/v1/auth/passkeys/config", json={"origin": "http://192.168.1.2"}
            ).status_code
            == 400
        )
        assert (
            client.put(
                "/api/v1/auth/passkeys/config", json={"origin": "https://media.test"}
            ).status_code
            == 200
        )
        options = client.post("/api/v1/auth/passkeys/register/options").json()["data"]
        credential_id = b"fake-test-credential"
        key_id = base64.urlsafe_b64encode(credential_id).decode().rstrip("=")
        calls = []

        def verify_registration(**kwargs):
            calls.append(kwargs)
            assert kwargs["require_user_verification"] is True
            assert kwargs["expected_rp_id"] == "media.test"
            assert kwargs["expected_origin"] == "https://media.test"
            return SimpleNamespace(
                credential_id=credential_id, credential_public_key=b"key", sign_count=0
            )

        monkeypatch.setattr(webauthn, "verify_registration_response", verify_registration)
        body = {"challenge_id": options["challenge_id"], "credential": {"id": key_id}}
        assert client.post("/api/v1/auth/passkeys/register/verify", json=body).status_code == 200
        assert client.post("/api/v1/auth/passkeys/register/verify", json=body).status_code == 401
        assert len(calls) == 1
        client.cookies.clear()
        options = client.post("/api/v1/auth/passkeys/login/options").json()["data"]

        def verify_authentication(**kwargs):
            assert kwargs["credential_public_key"] == b"key"
            assert kwargs["credential_current_sign_count"] == 0
            return SimpleNamespace(new_sign_count=1)

        monkeypatch.setattr(webauthn, "verify_authentication_response", verify_authentication)
        body["challenge_id"] = options["challenge_id"]
        assert client.post("/api/v1/auth/passkeys/login/verify", json=body).status_code == 200
        assert client.get("/api/v1/auth/status").json()["data"]["user"]["username"] == "admin"
        assert client.delete("/api/v1/auth/passkeys/" + key_id).status_code == 200


def test_invalid_passkey_is_rejected_by_real_verifier_and_rate_limited(tmp_path):
    with TestClient(create_app(app_settings(tmp_path))) as client:
        setup(client)
        client.put("/api/v1/auth/passkeys/config", json={"origin": "https://media.test"})
        options = client.post("/api/v1/auth/passkeys/register/options").json()["data"]
        assert (
            client.post(
                "/api/v1/auth/passkeys/register/verify",
                json={"challenge_id": options["challenge_id"], "credential": {"id": "forged"}},
            ).status_code
            == 401
        )
        for _ in range(10):
            assert (
                client.post(
                    "/api/v1/auth/login", json={"username": "admin", "password": "bad"}
                ).status_code
                == 401
            )
        assert (
            client.post(
                "/api/v1/auth/login", json={"username": "admin", "password": PASSWORD}
            ).status_code
            == 429
        )
