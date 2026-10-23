from fastapi import APIRouter

from app.api.v1 import (
    access,
    automation,
    automation_features,
    error_logs,
    images,
    mcp,
    media,
    system,
)

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(system.router)
api_router.include_router(error_logs.router)
api_router.include_router(media.router)
api_router.include_router(images.router)
api_router.include_router(automation.router)
api_router.include_router(automation_features.router)
api_router.include_router(access.router)
api_router.include_router(mcp.router)
