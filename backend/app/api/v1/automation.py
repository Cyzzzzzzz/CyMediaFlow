from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from app.api.response import ok
from app.application.automation_service import AutomationService, public_feed, public_subscription
from app.container import Container
from app.core.errors import DomainError

router = APIRouter(prefix="/automation", tags=["automation"])


def service(request: Request) -> AutomationService:
    container: Container = request.app.state.container
    return container.automation_service


Automation = Annotated[AutomationService, Depends(service)]


class ConfigUpdate(BaseModel):
    enabled: bool = False
    interval_minutes: int = Field(default=15, ge=1, le=1440)
    qb_url: str = ""
    qb_username: str = ""
    qb_save_root: str = ""
    rss_proxy_url: str = ""
    qb_password: str | None = None
    clear_qb_password: bool = False


class FeedUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    url: str | None = None
    enabled: bool = True


class SubscriptionUpdate(BaseModel):
    feed_id: int
    title: str = Field(min_length=1, max_length=180)
    folder_name: str = Field(default="", max_length=180)
    aliases: list[str] = Field(default_factory=list)
    season: int = Field(default=1, ge=0, le=99)
    episode_offset: int = Field(default=0, ge=-999, le=999)
    preferred_group: str | None = None
    preferred_resolution: str | None = None
    exclude_keywords: list[str] = Field(default_factory=list)
    enabled: bool = True


@router.get("/settings")
def get_settings(request: Request, automation: Automation) -> dict:
    return ok(request, automation.get_config())


@router.put("/settings")
def put_settings(body: ConfigUpdate, request: Request, automation: Automation) -> dict:
    return ok(request, automation.save_config(**body.model_dump()))


@router.post("/downloader/test")
async def test_downloader(request: Request, automation: Automation) -> dict:
    return ok(request, {"version": await automation.test_downloader()})


@router.get("/feeds")
def list_feeds(request: Request, automation: Automation) -> dict:
    return ok(request, [public_feed(row) for row in automation._repo.list_feeds()])


@router.post("/feeds")
def add_feed(body: FeedUpdate, request: Request, automation: Automation) -> dict:
    return ok(request, automation.save_feed(None, **body.model_dump()))


@router.put("/feeds/{feed_id}")
def edit_feed(feed_id: int, body: FeedUpdate, request: Request, automation: Automation) -> dict:
    return ok(request, automation.save_feed(feed_id, **body.model_dump()))


@router.delete("/feeds/{feed_id}")
def remove_feed(feed_id: int, request: Request, automation: Automation) -> dict:
    automation.delete_feed(feed_id)
    return ok(request, {"deleted": True})


@router.post("/feeds/{feed_id}/preview")
async def preview_feed(feed_id: int, request: Request, automation: Automation) -> dict:
    return ok(request, await automation.preview_feed(feed_id))


@router.post("/feeds/{feed_id}/refresh")
async def refresh_feed(feed_id: int, request: Request, automation: Automation) -> dict:
    return ok(request, await automation.refresh_feed(feed_id))


@router.get("/subscriptions")
def list_subscriptions(request: Request, automation: Automation) -> dict:
    return ok(request, [public_subscription(row) for row in automation._repo.list_subscriptions()])


@router.post("/subscriptions")
def add_subscription(body: SubscriptionUpdate, request: Request, automation: Automation) -> dict:
    return ok(request, automation.save_subscription(None, body.model_dump()))


@router.put("/subscriptions/{subscription_id}")
def edit_subscription(
    subscription_id: int, body: SubscriptionUpdate, request: Request, automation: Automation
) -> dict:
    return ok(request, automation.save_subscription(subscription_id, body.model_dump()))


@router.delete("/subscriptions/{subscription_id}")
def remove_subscription(subscription_id: int, request: Request, automation: Automation) -> dict:
    automation.delete_subscription(subscription_id)
    return ok(request, {"deleted": True})


@router.get("/releases")
def list_releases(request: Request, automation: Automation, feed_id: int | None = None) -> dict:
    return ok(
        request,
        [
            {
                "id": row.id,
                "feed_id": row.feed_id,
                "title": row.title,
                "analysis": row.parsed,
                "decision": row.decision,
                "reason": row.reason,
            }
            for row in automation._repo.list_releases(feed_id)
        ],
    )


@router.get("/downloads")
def list_downloads(request: Request, automation: Automation) -> dict:
    return ok(
        request,
        [
            {
                "id": row.id,
                "release_id": row.release_id,
                "subscription_id": row.subscription_id,
                "torrent_hash": row.torrent_hash,
                "state": row.state,
                "progress": row.progress,
                "error": row.error,
                "save_path": row.save_path,
                "created_at": row.created_at,
            }
            for row in automation._repo.list_downloads()
        ],
    )


@router.post("/downloads/sync")
async def sync_downloads(request: Request, automation: Automation) -> dict:
    await automation.sync_downloads()
    return ok(request, {"synced": True})


@router.post("/run")
async def run_cycle(request: Request, automation: Automation) -> dict:
    if not automation.get_config().enabled:
        raise DomainError("AUTOMATION_DISABLED", "请先在设置中启用自动追番")
    return ok(request, await automation.run_once())


@router.get("/events")
def list_events(request: Request, automation: Automation) -> dict:
    return ok(
        request,
        [
            {
                "id": row.id,
                "kind": row.kind,
                "message": row.message,
                "feed_id": row.feed_id,
                "download_id": row.download_id,
                "created_at": row.created_at,
            }
            for row in automation._repo.list_events()
        ],
    )
