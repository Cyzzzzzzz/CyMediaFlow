from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

from fastapi import APIRouter, Request

from app.api.dependencies import get_container
from app.api.response import ok
from app.api.schemas import BangumiProxyUpdate, SettingsUpdate, SettingsView
from app.container import build_container
from app.core.errors import DomainError
from app.core.path_safety import path_is_within

router = APIRouter(tags=["system"])


@router.get("/system/health")
def health(request: Request) -> dict[str, object]:
    return ok(request, {"status": "ok", "version": "0.1.0"})


@router.get("/settings")
def settings(request: Request) -> dict[str, object]:
    container = get_container(request)
    return ok(request, _settings_view(container).model_dump(mode="json"))


@router.put("/settings/bangumi-proxy")
def update_bangumi_proxy(
    body: BangumiProxyUpdate,
    request: Request,
) -> dict[str, object]:
    container = get_container(request)
    proxy_url = str(body.url) if body.enabled else None
    container.app_settings.set("bangumi_proxy_url", proxy_url or "")
    container.bangumi.set_proxy_url(proxy_url)
    container.image_proxy.set_proxy_url(proxy_url)
    return ok(request, _settings_view(container).model_dump(mode="json"))


@router.put("/settings")
def update_settings(body: SettingsUpdate, request: Request) -> dict[str, object]:
    container = get_container(request)
    media_root = _validated_media_root(body.media_root, container.settings.allowed_media_roots)
    values = {
        "media_root": str(media_root),
        "bangumi_proxy_url": (
            str(body.bangumi_proxy_url)
            if body.bangumi_proxy_enabled and body.bangumi_proxy_url
            else ""
        ),
        "tmdb_proxy_url": (
            str(body.tmdb_proxy_url) if body.tmdb_proxy_enabled and body.tmdb_proxy_url else ""
        ),
        "operation_mode": body.operation_mode,
        "episode_artwork_fallback_enabled": str(
            body.episode_artwork_fallback_enabled
        ).casefold(),
        "episode_artwork_capture_percent": str(body.episode_artwork_capture_percent),
    }
    if body.ignore_marker_enabled is not None:
        values["ignore_marker_enabled"] = str(body.ignore_marker_enabled).casefold()
    if body.ignore_folder_patterns is not None:
        values["ignore_folder_patterns"] = json.dumps(
            body.ignore_folder_patterns, ensure_ascii=False
        )
    if body.ffprobe_path:
        values["ffprobe_path"] = body.ffprobe_path.strip()
    if body.ffmpeg_path:
        values["ffmpeg_path"] = body.ffmpeg_path.strip()
    if body.clear_bangumi_access_token:
        values["bangumi_access_token"] = ""
    elif body.bangumi_access_token and body.bangumi_access_token.strip():
        values["bangumi_access_token"] = body.bangumi_access_token.strip()
    if body.clear_tmdb_access_token:
        values["tmdb_access_token"] = ""
    elif body.tmdb_access_token and body.tmdb_access_token.strip():
        values["tmdb_access_token"] = body.tmdb_access_token.strip()
    for key, value in values.items():
        container.app_settings.set(key, value)

    request.app.state.container = build_container(container.settings)
    return ok(request, _settings_view(request.app.state.container).model_dump(mode="json"))


def _settings_view(container) -> SettingsView:
    root = container.settings.media_root
    ignore_result = container.ignore_markers.last_result
    return SettingsView(
        media_root=str(root),
        allowed_media_root=str(container.settings.allowed_media_root),
        allowed_media_roots=[str(value) for value in container.settings.allowed_media_roots],
        media_root_exists=root.is_dir(),
        media_root_readable=root.is_dir() and os.access(root, os.R_OK),
        bangumi_configured=container.bangumi.configured,
        bangumi_api_url=container.settings.bangumi_api_url,
        tmdb_configured=container.tmdb.configured,
        tmdb_api_url=container.settings.tmdb_api_url,
        operation_mode=container.settings.operation_mode,
        bangumi_proxy_enabled=container.bangumi.proxy_url is not None,
        bangumi_proxy_url=container.bangumi.proxy_url,
        tmdb_proxy_enabled=container.tmdb.proxy_url is not None,
        tmdb_proxy_url=container.tmdb.proxy_url,
        episode_artwork_fallback_enabled=container.settings.episode_artwork_fallback_enabled,
        episode_artwork_capture_percent=container.settings.episode_artwork_capture_percent,
        ffprobe_path=container.settings.ffprobe_path,
        ffprobe_available=_executable_available(container.settings.ffprobe_path),
        ffmpeg_path=container.settings.ffmpeg_path,
        ffmpeg_available=_executable_available(container.settings.ffmpeg_path),
        ignore_marker_enabled=container.settings.ignore_marker_enabled,
        ignore_folder_patterns=list(container.settings.ignore_folder_patterns),
        ignore_marker_matched_count=ignore_result.matched_count,
        ignore_marker_created_count=ignore_result.created_count,
        ignore_marker_existing_count=ignore_result.existing_count,
        ignore_marker_failed_count=ignore_result.failed_count,
    )


def _executable_available(executable: str) -> bool:
    return shutil.which(executable) is not None


def _validated_media_root(value: str, allowed_root: Path | tuple[Path, ...]) -> Path:
    requested = Path(value.strip()).expanduser()
    allowed_roots = allowed_root if isinstance(allowed_root, tuple) else (allowed_root,)
    allowed = tuple(root.resolve(strict=False) for root in allowed_roots)
    relative_base = allowed[0]
    candidate = (
        requested if requested.is_absolute() else relative_base / requested
    ).resolve(strict=False)
    if not any(path_is_within(candidate, root) for root in allowed):
        raise DomainError(
            code="MEDIA_ROOT_OUTSIDE_ALLOWED_ROOT",
            message=(
                "媒体目录必须位于允许范围内；Docker/NAS 请填写容器路径，"
                "通常为 /media 或其子目录"
            ),
            status_code=400,
            details={
                "requested_media_root": value,
                "resolved_media_root": str(candidate),
                "allowed_media_roots": [str(root) for root in allowed],
            },
        )
    if not candidate.is_dir() or not os.access(candidate, os.R_OK):
        raise DomainError(
            code="MEDIA_ROOT_NOT_READABLE",
            message="媒体目录不存在或当前进程不可读取",
            status_code=400,
            details={"media_root": str(candidate)},
        )
    return candidate
