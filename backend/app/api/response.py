from __future__ import annotations

from typing import Any

from fastapi import Request


def ok(request: Request, data: Any) -> dict[str, Any]:
    return {
        "success": True,
        "data": data,
        "meta": None,
        "error": None,
        "request_id": request.state.request_id,
    }


def failed(
    request: Request,
    code: str,
    message: str,
    details: dict[str, object] | None = None,
) -> dict[str, Any]:
    return {
        "success": False,
        "data": None,
        "meta": None,
        "error": {"code": code, "message": message, "details": details or {}},
        "request_id": request.state.request_id,
    }
