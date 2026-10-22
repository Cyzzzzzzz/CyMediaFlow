from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from fastapi.testclient import TestClient
from test_automation import app_settings
from test_automation_extensions import MultiQb, release, rule

from app.application.automation_service import AutomationService
from app.infrastructure.persistence.database import AutomationFileOperationRecord
from app.main import create_app

LEGACY_WAIT_REASON = "等待下载器确认重命名"


class DeferredRenameQb(MultiQb):
    """Accept renameFile immediately, publish its effects only when explicitly completed."""

    def __init__(self, root: Path):
        super().__init__(root)
        self.pending: list[tuple[str, str, str]] = []

    async def rename_file(self, task_hash, source, target):
        operation = (task_hash, source, target)
        self.renames.append(operation)
        self.pending.append(operation)

    def complete_pending(self):
        for task_hash, source, target in self.pending:
            task = self.tasks[task_hash]
            target_path = task["directory"] / target
            target_path.parent.mkdir(parents=True, exist_ok=True)
            assert not target_path.exists(), "a deferred rename would overwrite a file"
            (task["directory"] / source).rename(target_path)
            task["names"][task["names"].index(source)] = target
        self.pending.clear()


def create_download(client: TestClient):
    subscription_id = rule(client)["id"]
    service = client.app.state.container.automation_service
    candidate = release(service, subscription_id)
    response = client.post(
        f"/api/v1/automation/releases/{candidate.id}/download",
        json={"subscription_id": subscription_id, "confirm": True},
    )
    assert response.status_code == 200, response.text
    assert response.json()["data"]["confirmed"] is True
    return service, service._repo.get_download_by_release(candidate.id)


@pytest.fixture
def deferred_job(tmp_path, monkeypatch):
    settings = app_settings(tmp_path)
    qb = DeferredRenameQb(settings.media_root)
    monkeypatch.setattr(AutomationService, "_qb", lambda self: qb)
    with TestClient(create_app(settings)) as client:
        service, job = create_download(client)
        yield client, service, qb, job


def sync(client: TestClient, service, job_id):
    response = client.post("/api/v1/automation/downloads/sync")
    assert response.status_code == 200, response.text
    return service._repo.get_download(job_id)


def age_operation(service, operation_id, *, seconds=180):
    with service._repo._factory() as session:
        operation = session.get(AutomationFileOperationRecord, operation_id)
        operation.updated_at = datetime.now(timezone.utc) - timedelta(seconds=seconds)
        session.commit()


def test_delayed_rename_waits_then_confirms_on_next_sync(deferred_job):
    client, service, qb, job = deferred_job

    waiting = sync(client, service, job.id)
    assert waiting.state == "waiting_rename", waiting.error
    assert len(qb.renames) == 1
    assert service._repo.list_operations(job.id)[0].state == "running"
    assert service._repo.get_release(job.release_id).decision == "waiting_rename"
    assert job.id in {row.id for row in service._repo.list_pending_downloads()}
    assert not [event for event in service._repo.list_events() if event.kind == "review"]

    qb.complete_pending()
    finished = sync(client, service, job.id)

    assert finished.state == "organized", finished.error
    assert finished.error is None
    assert len(qb.renames) == 1
    assert service._repo.list_operations(job.id)[0].state == "done"
    candidate = service._repo.get_release(job.release_id)
    assert candidate.decision == "queued"
    assert candidate.reason is None
    assert (Path(job.local_path) / "Hero S01E01.mkv").read_bytes() == b"version-1"


def test_pending_rename_does_not_repeat_request_or_extend_deadline(deferred_job):
    client, service, qb, job = deferred_job
    assert sync(client, service, job.id).state == "waiting_rename"
    original_timestamp = service._repo.list_operations(job.id)[0].updated_at

    for _ in range(3):
        assert sync(client, service, job.id).state == "waiting_rename"
        operation = service._repo.list_operations(job.id)[0]
        assert operation.state == "running"
        assert operation.updated_at == original_timestamp
    assert len(qb.renames) == 1
    assert (
        len([event for event in service._repo.list_events() if event.kind == "rename_pending"]) == 1
    )


def test_pending_rename_cannot_be_restored_before_it_is_confirmed(deferred_job):
    client, service, qb, job = deferred_job
    assert sync(client, service, job.id).state == "waiting_rename"

    response = client.post(
        f"/api/v1/automation/downloads/{job.id}/action",
        json={"action": "restore", "confirm": True},
    )

    assert response.status_code == 409, response.text
    assert service._repo.list_operations(job.id)[0].state == "running"
    assert len(qb.renames) == 1
    qb.complete_pending()
    assert sync(client, service, job.id).state == "organized"


def test_filesystem_rename_can_precede_downloader_file_list(deferred_job):
    client, service, qb, job = deferred_job
    assert sync(client, service, job.id).state == "waiting_rename"
    _, source, target = qb.pending[0]
    directory = Path(job.local_path)
    (directory / source).rename(directory / target)

    assert sync(client, service, job.id).state == "waiting_rename"
    assert len(qb.renames) == 1
    task = qb.tasks[job.qb_tag]
    task["names"][task["names"].index(source)] = target
    qb.pending.clear()
    assert sync(client, service, job.id).state == "organized"
    assert len(qb.renames) == 1


def test_pending_rename_timeout_requires_review_without_resubmitting(deferred_job):
    client, service, qb, job = deferred_job
    assert sync(client, service, job.id).state == "waiting_rename"
    operation = service._repo.list_operations(job.id)[0]
    age_operation(service, operation.id)

    failed = sync(client, service, job.id)
    assert failed.state == "review"
    assert "超时" in failed.error
    assert failed.error != LEGACY_WAIT_REASON
    assert len(qb.renames) == 1
    assert service._repo.list_operations(job.id)[0].state == "failed"
    assert job.id not in {row.id for row in service._repo.list_pending_downloads()}
    assert service._repo.get_release(job.release_id).decision == "review"
    assert sync(client, service, job.id).state == "review"
    assert len(qb.renames) == 1


def test_expired_rename_can_only_be_resubmitted_after_manual_continue(deferred_job):
    client, service, qb, job = deferred_job
    assert sync(client, service, job.id).state == "waiting_rename"
    operation = service._repo.list_operations(job.id)[0]
    age_operation(service, operation.id)
    assert sync(client, service, job.id).state == "review"
    assert len(qb.renames) == 1
    qb.pending.clear()  # Simulate the original request never completing in qB.

    response = client.post(
        f"/api/v1/automation/downloads/{job.id}/action", json={"action": "organize"}
    )

    assert response.status_code == 200, response.text
    assert response.json()["data"]["state"] == "waiting_rename"
    assert len(qb.renames) == 2
    qb.complete_pending()
    assert sync(client, service, job.id).state == "organized"
    assert len(qb.renames) == 2


@pytest.mark.parametrize("operation_state", ["running", "done"])
def test_legacy_review_recovers_after_restart_even_with_old_operation(
    tmp_path, monkeypatch, operation_state
):
    settings = app_settings(tmp_path)
    qb = DeferredRenameQb(settings.media_root)
    monkeypatch.setattr(AutomationService, "_qb", lambda self: qb)
    with TestClient(create_app(settings)) as client:
        service, job = create_download(client)
        sync(client, service, job.id)
        qb.complete_pending()
        operation = service._repo.list_operations(job.id)[0]
        service._repo.update_operation(operation.id, operation_state)
        age_operation(service, operation.id, seconds=86400)
        service._repo.update_download(job.id, state="review", error=LEGACY_WAIT_REASON)
        service._repo.set_release_decision(job.release_id, "review", LEGACY_WAIT_REASON)

    with TestClient(create_app(settings)) as restarted_client:
        restarted = restarted_client.app.state.container.automation_service
        finished = sync(restarted_client, restarted, job.id)
        assert finished.state == "organized", finished.error
        assert finished.error is None
        candidate = restarted._repo.get_release(job.release_id)
        assert candidate.decision == "queued"
        assert candidate.reason is None
        assert restarted._repo.list_operations(job.id)[0].state == "done"
        assert len(qb.renames) == 1


def test_manual_continue_clears_stale_release_review(deferred_job):
    client, service, qb, job = deferred_job
    sync(client, service, job.id)
    qb.complete_pending()
    service._repo.update_download(job.id, state="review", error=LEGACY_WAIT_REASON)
    service._repo.set_release_decision(job.release_id, "review", LEGACY_WAIT_REASON)

    response = client.post(
        f"/api/v1/automation/downloads/{job.id}/action", json={"action": "organize"}
    )

    assert response.status_code == 200, response.text
    assert response.json()["data"]["state"] == "organized"
    candidate = service._repo.get_release(job.release_id)
    assert candidate.decision == "queued"
    assert candidate.reason is None
    assert len(qb.renames) == 1


def test_excluded_candidate_is_not_unexcluded_by_waiting_or_success(deferred_job):
    client, service, qb, job = deferred_job
    service._repo.set_release_decision(job.release_id, "excluded", "用户手动排除")

    assert sync(client, service, job.id).state == "waiting_rename"
    assert service._repo.get_release(job.release_id).decision == "excluded"
    qb.complete_pending()
    assert sync(client, service, job.id).state == "organized"
    candidate = service._repo.get_release(job.release_id)
    assert candidate.decision == "excluded"
    assert candidate.reason == "用户手动排除"


def test_existing_destination_conflict_stays_review_without_overwriting(deferred_job):
    client, service, qb, job = deferred_job
    target = Path(job.local_path) / "Hero S01E01.mkv"
    target.write_bytes(b"unrelated-video")

    failed = sync(client, service, job.id)

    assert failed.state == "review"
    assert failed.error != LEGACY_WAIT_REASON
    assert target.read_bytes() == b"unrelated-video"
    assert qb.renames == []
    assert job.id not in {row.id for row in service._repo.list_pending_downloads()}


def test_both_downloader_names_are_a_conflict_not_success(deferred_job):
    client, service, qb, job = deferred_job
    assert sync(client, service, job.id).state == "waiting_rename"
    task = qb.tasks[job.qb_tag]
    task["names"].append("Hero S01E01.mkv")
    target = Path(job.local_path) / "Hero S01E01.mkv"
    target.write_bytes(b"unrelated-video")

    failed = sync(client, service, job.id)

    assert failed.state == "review"
    assert target.read_bytes() == b"unrelated-video"
    assert len(qb.renames) == 1
    assert job.id not in {row.id for row in service._repo.list_pending_downloads()}


def test_confirmed_name_waits_for_media_mount_before_reporting_success(deferred_job):
    client, service, qb, job = deferred_job
    assert sync(client, service, job.id).state == "waiting_rename"
    qb.complete_pending()
    target = Path(job.local_path) / "Hero S01E01.mkv"
    temporarily_unmounted = target.with_suffix(".pending")
    target.rename(temporarily_unmounted)

    waiting = sync(client, service, job.id)

    assert waiting.state == "waiting_files"
    assert service._repo.list_operations(job.id)[0].state == "done"
    assert len(qb.renames) == 1
    temporarily_unmounted.rename(target)
    assert sync(client, service, job.id).state == "organized"
    assert len(qb.renames) == 1


def test_lost_rename_response_is_reconciled_without_repeating_request(deferred_job):
    client, service, qb, job = deferred_job
    accepted = qb.rename_file

    async def timeout_after_accepting(*args):
        await accepted(*args)
        raise httpx.ReadTimeout("qB accepted rename but its response was lost")

    qb.rename_file = timeout_after_accepting
    assert sync(client, service, job.id).state == "retry_sync"
    assert service._repo.list_operations(job.id)[0].state == "running"
    assert sync(client, service, job.id).state == "waiting_rename"
    assert len(qb.renames) == 1

    qb.complete_pending()
    assert sync(client, service, job.id).state == "organized"
    assert len(qb.renames) == 1


def test_multi_file_plan_resumes_after_each_async_confirmation(deferred_job):
    client, service, qb, job = deferred_job
    task = qb.tasks[job.qb_tag]
    subtitle = "[ANi] Hero - 01.chs.ass"
    task["names"].append(subtitle)
    (task["directory"] / subtitle).write_bytes(b"subtitle")

    assert sync(client, service, job.id).state == "waiting_rename"
    assert len(qb.renames) == 1
    qb.complete_pending()
    assert sync(client, service, job.id).state == "waiting_rename"
    assert len(qb.renames) == 2
    qb.complete_pending()
    assert sync(client, service, job.id).state == "organized"

    assert len(set(qb.renames)) == len(qb.renames) == 2
    assert all(operation.state == "done" for operation in service._repo.list_operations(job.id))
    assert (Path(job.local_path) / "Hero S01E01.mkv").read_bytes() == b"version-1"
    assert (Path(job.local_path) / "Hero S01E01.sc.ass").read_bytes() == b"subtitle"


@pytest.mark.parametrize("finished_state", ["organized", "revision_ready"])
def test_completed_job_clears_legacy_candidate_review_without_downloader_access(
    deferred_job, finished_state
):
    client, service, _, job = deferred_job
    service._repo.update_download(job.id, state=finished_state, error=None)
    service._repo.set_release_decision(job.release_id, "review", LEGACY_WAIT_REASON)
    service.downloader = Mock(side_effect=AssertionError("completed job must not contact qB"))
    service.operations.auto_organize = AsyncMock(
        side_effect=AssertionError("completed job must not replay its file plan")
    )

    assert sync(client, service, job.id).state == finished_state

    candidate = service._repo.get_release(job.release_id)
    assert candidate.decision == "queued"
    assert candidate.reason is None
    service.downloader.assert_not_called()
    service.operations.auto_organize.assert_not_awaited()
    assert job.id not in {row.id for row in service._repo.list_pending_downloads()}


@pytest.mark.parametrize(
    ("reason", "operation_state"),
    [
        ("文件状态与整理计划冲突", "running"),
        ("下载器重命名确认超时，请人工核对", "running"),
        (LEGACY_WAIT_REASON, None),
        (LEGACY_WAIT_REASON, "planned"),
        (LEGACY_WAIT_REASON, "restored"),
    ],
)
def test_recovery_does_not_admit_unrelated_reviews(deferred_job, reason, operation_state):
    _, service, qb, job = deferred_job
    if operation_state:
        source = qb.tasks[job.qb_tag]["names"][0]
        operation = service._repo.plan_operation(job.id, source, "Hero S01E01.mkv")
        service._repo.update_operation(operation.id, operation_state)
    service._repo.update_download(job.id, state="review", progress=100, error=reason)

    assert job.id not in {row.id for row in service._repo.list_pending_downloads()}
    assert qb.renames == []
