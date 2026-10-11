import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi.testclient import TestClient

from app.infrastructure.automation import torrent_source
from app.infrastructure.automation.qbittorrent import QbittorrentClient, QbittorrentError
from app.infrastructure.automation.rss import FeedEntry
from app.infrastructure.automation.torrent_source import TorrentSourceError, fetch_torrent
from app.infrastructure.persistence.database import AutomationDownloadRecord
from app.main import create_app
from tests.test_automation import app_settings


def test_http_torrent_is_downloaded_via_rss_proxy_then_uploaded_to_lan(monkeypatch):
    clients, uploads = [], []
    torrent = b"d4:infod4:name4:hero6:lengthi1eee"

    def handler(request):
        if request.url.host == "source.test":
            return httpx.Response(200, content=torrent)
        assert request.url.host == "qb.test"
        if request.url.path.endswith("/auth/login"):
            return httpx.Response(200, text="Ok.")
        assert request.url.path.endswith("/torrents/add")
        uploads.append(request.content)
        assert "multipart/form-data" in request.headers["content-type"]
        return httpx.Response(200, text="Ok.")

    original = httpx.AsyncClient

    def client(**kwargs):
        clients.append(dict(kwargs))
        kwargs.pop("proxy", None)  # Mock only; real clients receive the configured proxy.
        return original(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", client)
    qb = QbittorrentClient("http://qb.test", "test", "password", "http://proxy.test:20181")
    assert asyncio.run(
        qb.add("https://source.test/a.torrent?private=secret", "/downloads/Hero", "cymf-1")
    )
    assert clients[0]["proxy"] == "http://proxy.test:20181"
    assert "proxy" not in clients[1] and clients[1]["trust_env"] is False
    assert torrent in uploads[0]
    assert b'name="torrents"; filename="release.torrent"' in uploads[0]
    assert b"private=secret" not in uploads[0]
    assert b"/downloads/Hero" in uploads[0] and b"cymf-1" in uploads[0]


@pytest.mark.parametrize("scenario", ["html", "oversized", "http_error", "timeout"])
def test_torrent_failures_are_bounded_and_do_not_expose_private_urls(monkeypatch, scenario):
    def handler(request):
        if scenario == "timeout":
            raise httpx.ReadTimeout("https://source.test/file?private=secret", request=request)
        if scenario == "http_error":
            return httpx.Response(403)
        return httpx.Response(
            200, content=b"<html>login</html>" if scenario == "html" else b"d" + b"x" * 50 + b"e"
        )

    original = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs),
    )
    monkeypatch.setattr(torrent_source, "MAX_TORRENT_BYTES", 40)
    with pytest.raises(TorrentSourceError) as caught:
        asyncio.run(fetch_torrent("https://source.test/file?private=secret", None))
    assert "secret" not in str(caught.value)
    assert "source.test" not in str(caught.value)


class PendingDownloader:
    def __init__(self):
        self.visible = False
        self.confirm_on_add = False
        self.add_calls = 0
        self.failure = None

    async def by_tag(self, _tag):
        return [{"hash": "confirmed-hash", "progress": 0.25}] if self.visible else []

    async def add(self, *_args):
        self.add_calls += 1
        if self.failure:
            raise self.failure
        self.visible = self.confirm_on_add
        return True  # qB accepted the request, but may not create any torrent.


def setup_download(client):
    automation = client.app.state.container.automation_service
    fake = PendingDownloader()
    automation._qb = lambda: fake
    automation._rss.fetch = AsyncMock(
        return_value=[FeedEntry("one", "[ANi] Hero - 01 [1080P].mkv", "magnet:?xt=urn:btih:test")]
    )
    saved = client.post(
        "/api/v1/automation/subscriptions/confirm",
        json={"url": "https://rss.test/feed", "rules": [{"title": "Hero"}]},
    ).json()["data"]
    assert (
        client.put(
            "/api/v1/automation/settings",
            json={
                "enabled": True,
                "qb_url": "http://qb.test",
                "qb_username": "admin",
                "qb_password": "test",
                "qb_save_root": "/downloads",
            },
        ).status_code
        == 200
    )
    return automation, fake, saved


def age_job(automation, job_id):
    with automation._repo._factory() as session:
        session.get(AutomationDownloadRecord, job_id).updated_at = datetime.now(
            timezone.utc
        ) - timedelta(minutes=5)
        session.commit()


def test_ok_response_is_pending_until_actual_torrent_is_visible(tmp_path: Path):
    with TestClient(create_app(app_settings(tmp_path))) as client:
        automation, fake, saved = setup_download(client)
        refresh = f"/api/v1/automation/feeds/{saved['feed']['id']}/refresh"
        assert client.post(refresh).json()["data"] == {
            "fetched": 1,
            "submitted": 0,
            "pending": 1,
            "failed": 0,
        }
        job = automation._repo.list_downloads()[0]
        assert job.state == "confirming" and job.torrent_hash is None
        assert not any(row.kind == "download_added" for row in automation._repo.list_events())
        client.post(refresh)
        assert fake.add_calls == 1
        assert client.post(f"/api/v1/automation/downloads/{job.id}/retry").status_code == 409
        fake.visible = True
        client.post("/api/v1/automation/downloads/sync")
        job = automation._repo.get_download(job.id)
        assert job.state == "downloading" and job.torrent_hash == "confirmed-hash"
        client.post(refresh)
        assert fake.add_calls == 1


def test_timeout_exposes_retry_and_reuses_the_existing_job(tmp_path: Path):
    with TestClient(create_app(app_settings(tmp_path))) as client:
        automation, fake, saved = setup_download(client)
        client.post(f"/api/v1/automation/feeds/{saved['feed']['id']}/refresh")
        job = automation._repo.list_downloads()[0]
        # An old version's misleading submitted state also recovers without deleting its DB row.
        automation._repo.update_download(job.id, state="submitted")
        age_job(automation, job.id)
        client.post("/api/v1/automation/downloads/sync")
        assert automation._repo.get_download(job.id).state == "missing"
        fake.confirm_on_add = True
        result = client.post(f"/api/v1/automation/downloads/{job.id}/retry")
        assert result.json()["data"]["confirmed"] is True
        assert len(automation._repo.list_downloads()) == 1
        assert automation._repo.get_download(job.id).qb_tag == job.qb_tag
        assert fake.add_calls == 2
        assert client.post(f"/api/v1/automation/downloads/{job.id}/retry").status_code == 409


@pytest.mark.parametrize("already_confirmed", [False, True])
def test_deleted_then_recreated_rule_recovers_failed_releases_only(
    tmp_path: Path, already_confirmed
):
    with TestClient(create_app(app_settings(tmp_path))) as client:
        automation, fake, saved = setup_download(client)
        fake.confirm_on_add = already_confirmed
        refresh = f"/api/v1/automation/feeds/{saved['feed']['id']}/refresh"
        client.post(refresh)
        job = automation._repo.list_downloads()[0]
        client.delete(f"/api/v1/automation/subscriptions/{saved['rules'][0]['id']}")
        replacement = client.post(
            "/api/v1/automation/subscriptions/confirm",
            json={"url": "https://rss.test/feed", "rules": [{"title": "Hero"}]},
        ).json()["data"]["rules"][0]
        assert replacement["id"] != job.subscription_id
        if not already_confirmed:
            automation._repo.update_download(job.id, state="submitted")
            age_job(automation, job.id)
        fake.confirm_on_add = True
        result = client.post(refresh).json()["data"]
        assert result["submitted"] == (0 if already_confirmed else 1)
        assert fake.add_calls == (1 if already_confirmed else 2)
        assert len(automation._repo.list_downloads()) == 1
        updated = automation._repo.get_download(job.id)
        assert updated.subscription_id == (
            job.subscription_id if already_confirmed else replacement["id"]
        )
        assert updated.naming_json == job.naming_json
        # Further refreshes must never resubmit a confirmed torrent.
        client.post(refresh)
        assert fake.add_calls == (1 if already_confirmed else 2)


def test_failed_submission_reports_source_error_and_disabled_rule_does_not_retry(tmp_path: Path):
    with TestClient(create_app(app_settings(tmp_path))) as client:
        automation, fake, saved = setup_download(client)
        fake.failure = TorrentSourceError("种子文件获取失败；请检查 RSS 代理")
        result = client.post(f"/api/v1/automation/feeds/{saved['feed']['id']}/refresh").json()[
            "data"
        ]
        assert result["failed"] == 1 and result["submitted"] == 0
        job = automation._repo.list_downloads()[0]
        assert job.state == "retry" and "RSS 代理" in job.error
        client.delete(f"/api/v1/automation/subscriptions/{saved['rules'][0]['id']}")
        client.post("/api/v1/automation/downloads/sync")
        assert fake.add_calls == 1
        assert client.post(f"/api/v1/automation/downloads/{job.id}/retry").status_code == 400


def test_response_lost_after_add_does_not_resubmit_during_confirmation_grace(tmp_path: Path):
    with TestClient(create_app(app_settings(tmp_path))) as client:
        automation, fake, saved = setup_download(client)
        fake.failure = httpx.ReadTimeout("credentials-should-not-be-shown")
        refresh = f"/api/v1/automation/feeds/{saved['feed']['id']}/refresh"
        client.post(refresh)
        job = automation._repo.list_downloads()[0]
        assert job.state == "confirming" and "credentials" not in job.error
        client.post(refresh)
        assert fake.add_calls == 1


def test_failed_post_add_list_query_does_not_claim_definite_rejection(tmp_path: Path):
    with TestClient(create_app(app_settings(tmp_path))) as client:
        automation, fake, saved = setup_download(client)
        fake.by_tag = AsyncMock(
            side_effect=[[], QbittorrentError("qBittorrent 返回无效的任务列表")]
        )
        client.post(f"/api/v1/automation/feeds/{saved['feed']['id']}/refresh")
        assert automation._repo.list_downloads()[0].state == "confirming"


def test_failed_source_is_not_submitted_twice_in_one_scheduled_cycle(tmp_path: Path):
    with TestClient(create_app(app_settings(tmp_path))) as client:
        automation, fake, _ = setup_download(client)
        fake.failure = TorrentSourceError("种子文件获取失败")
        client.post("/api/v1/automation/run")
        assert fake.add_calls == 1
        job = automation._repo.list_downloads()[0]
        assert job.state == "retry" and job.error == "种子文件获取失败"
        age_job(automation, job.id)
        client.post("/api/v1/automation/downloads/sync")
        assert fake.add_calls == 2


def test_removed_confirmed_torrent_is_not_downloaded_again(tmp_path: Path):
    with TestClient(create_app(app_settings(tmp_path))) as client:
        automation, fake, saved = setup_download(client)
        fake.confirm_on_add = True
        refresh = f"/api/v1/automation/feeds/{saved['feed']['id']}/refresh"
        client.post(refresh)
        fake.visible = False
        client.post("/api/v1/automation/downloads/sync")
        job = automation._repo.list_downloads()[0]
        assert job.state == "missing" and job.torrent_hash
        client.post(refresh)
        assert fake.add_calls == 1
        assert client.post(f"/api/v1/automation/downloads/{job.id}/retry").status_code == 409
