from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.api.automation_feature_schemas import (
    BackfillRequest,
    FeatureConfig,
    JobAction,
    OrganizeRequest,
    OrphanAdopt,
    ReleaseDownload,
    ResourceSearch,
    RevisionRequest,
)
from app.api.automation_schemas import SubscriptionDraft
from app.api.response import ok
from app.core.errors import DomainError

router = APIRouter(prefix="/automation", tags=["automation-features"])


@router.get("/features/settings")
def settings(request: Request):
    return ok(request, request.app.state.container.automation_features.public())


@router.put("/features/settings")
def save_settings(body: FeatureConfig, request: Request):
    return ok(request, request.app.state.container.automation_features.save(body.model_dump()))


@router.post("/aria2/test")
async def test_aria(request: Request):
    try:
        result = await request.app.state.container.automation_service.downloader(
            kind="aria2"
        ).test_connection()
    except Exception as exc:
        raise DomainError("ARIA2_FAILED", "aria2 连接失败，请检查 RPC 地址和密钥", 503) from exc
    return ok(request, {"version": result})


@router.get("/search")
def search_cache(request: Request):
    return ok(request, request.app.state.container.automation_search.cached())


@router.post("/search")
async def search(body: ResourceSearch, request: Request):
    return ok(
        request, await request.app.state.container.automation_search.search(**body.model_dump())
    )


class SearchSubscription(BaseModel):
    feed_id: int
    rule: SubscriptionDraft


@router.post("/search/subscribe")
def subscribe(body: SearchSubscription, request: Request):
    service = request.app.state.container.automation_service
    result = service.save_subscription(None, {**body.rule.model_dump(), "feed_id": body.feed_id})
    feed = service._repo.get_feed(body.feed_id)
    service.save_feed(feed.id, name=feed.name, url=None, enabled=True)
    return ok(request, result)


@router.post("/releases/{release_id}/download")
async def download(release_id: int, body: ReleaseDownload, request: Request):
    return ok(
        request,
        await request.app.state.container.automation_operations.download(
            release_id, **body.model_dump()
        ),
    )


@router.post("/releases/{release_id}/skip")
async def skip(release_id: int, request: Request):
    operations = request.app.state.container.automation_operations
    async with operations.service._lock:
        operations.release(release_id)
        operations.repo.set_release_decision(release_id, "excluded", "用户已排除此发布")
    return ok(request, {"skipped": True})


class LlmRequest(BaseModel):
    title: str = Field(min_length=1, max_length=1000)
    refresh: bool = False


@router.post("/parser/suggest")
async def suggest(body: LlmRequest, request: Request):
    return ok(
        request, await request.app.state.container.automation_llm.suggest(**body.model_dump())
    )


@router.post("/downloads/{job_id}/action")
async def action(job_id: int, body: JobAction, request: Request):
    return ok(
        request,
        await request.app.state.container.automation_operations.job_action(
            job_id, **body.model_dump()
        ),
    )


@router.get("/downloads/{job_id}/files")
async def files(job_id: int, request: Request):
    container = request.app.state.container
    job = container.automation_operations.job(job_id)
    if not job.torrent_hash:
        raise DomainError("DOWNLOAD_NOT_READY", "任务尚未创建")
    return ok(request, await container.automation_service.downloader(job).files(job.torrent_hash))


@router.post("/downloads/{job_id}/organize")
async def organize(job_id: int, body: OrganizeRequest, request: Request):
    return ok(
        request,
        await request.app.state.container.automation_operations.plan(job_id, **body.model_dump()),
    )


@router.post("/downloads/{job_id}/revision")
async def revision(job_id: int, body: RevisionRequest, request: Request):
    return ok(
        request,
        await request.app.state.container.automation_operations.revision(
            job_id, **body.model_dump()
        ),
    )


@router.post("/downloads/{job_id}/revision/restore")
async def restore_revision(job_id: int, body: RevisionRequest, request: Request):
    return ok(
        request,
        await request.app.state.container.automation_operations.revision(
            job_id, **body.model_dump(), restore=True
        ),
    )


@router.get("/subscriptions/{rule_id}/backfill")
def backfill(rule_id: int, request: Request):
    return ok(request, request.app.state.container.automation_operations.backfill(rule_id))


@router.post("/subscriptions/{rule_id}/backfill")
async def collect(rule_id: int, body: BackfillRequest, request: Request):
    return ok(
        request,
        await request.app.state.container.automation_operations.collect(
            rule_id, **body.model_dump()
        ),
    )


@router.get("/orphans")
async def orphans(request: Request):
    return ok(request, await request.app.state.container.automation_operations.orphans())


@router.post("/orphans/adopt")
async def adopt(body: OrphanAdopt, request: Request):
    return ok(
        request, await request.app.state.container.automation_operations.adopt(**body.model_dump())
    )


@router.get("/calendar")
def calendar(request: Request):
    return ok(request, request.app.state.container.automation_updates.calendar())


@router.post("/calendar/refresh")
async def refresh_calendar(request: Request):
    return ok(request, await request.app.state.container.automation_updates.refresh_calendar())


def principal_id(request: Request) -> str:
    return (getattr(request.state, "principal", None) or {}).get("id", "local")


@router.get("/notifications")
def notifications(request: Request):
    return ok(
        request, request.app.state.container.automation_updates.notifications(principal_id(request))
    )


class ReadThrough(BaseModel):
    through: int = Field(ge=0)


@router.post("/notifications/read")
def read_notifications(body: ReadThrough, request: Request):
    request.app.state.container.automation_updates.mark_read(body.through, principal_id(request))
    return ok(request, {"read": True})


@router.post("/notifications/test")
async def test_notification(request: Request):
    await request.app.state.container.automation_updates.webhook(
        {"id": "test", "kind": "test", "message": "CyMediaFlow 通知连接测试"}
    )
    return ok(request, {"sent": True})


@router.get("/version")
def version(request: Request):
    return ok(request, request.app.state.container.automation_updates.version())


@router.post("/version/check")
async def check_version(request: Request):
    return ok(request, await request.app.state.container.automation_updates.check_version())


@router.get("/stream")
async def stream(request: Request, after: int = Query(default=0, ge=0)):
    try:
        cursor = max(after, int(request.headers.get("Last-Event-ID", "0")))
    except ValueError:
        cursor = after

    async def events():
        nonlocal cursor
        started = datetime.now(timezone.utc)
        # Reconnect periodically so expired/revoked sessions are rechecked by middleware.
        while (datetime.now(timezone.utc) - started).total_seconds() < 60:
            if await request.is_disconnected():
                return
            rows = request.app.state.container.automation_service._repo.events_after(cursor)
            for row in rows:
                cursor = row.id
                payload = json.dumps(
                    jsonable_encoder(
                        {
                            "id": row.id,
                            "kind": row.kind,
                            "message": row.message,
                            "created_at": row.created_at,
                        }
                    ),
                    ensure_ascii=False,
                )
                yield f"id: {row.id}\nevent: update\ndata: {payload}\n\n"
            yield ": heartbeat\n\n"
            await asyncio.sleep(3)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
