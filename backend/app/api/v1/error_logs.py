from __future__ import annotations

import sqlite3
from typing import Literal

from fastapi import APIRouter, Query, Request

from app.api.response import ok
from app.core.errors import DomainError

router = APIRouter(prefix="/system/error-logs", tags=["system"])


@router.get("")
def error_logs(
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
    before_id: int | None = Query(default=None, ge=1),
    level: Literal["WARNING", "ERROR"] | None = None,
    request_id: str | None = Query(default=None, max_length=80),
    code: str | None = Query(default=None, max_length=100),
) -> dict:
    try:
        result = request.app.state.error_logs.list(
            limit=limit,
            before_id=before_id,
            level=level,
            request_id=request_id,
            code=code,
        )
    except (OSError, sqlite3.Error) as exc:
        raise DomainError("ERROR_LOG_UNAVAILABLE", "异常日志存储暂不可用", 503) from exc
    return ok(request, result)
