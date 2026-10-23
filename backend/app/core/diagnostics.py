from __future__ import annotations

import logging
import re
import sys
from contextvars import ContextVar
from pathlib import Path

import httpx

from app.core.errors import DomainError
from app.infrastructure.persistence.error_logs import ErrorLogStore

active_log_store: ContextVar[ErrorLogStore | None] = ContextVar("error_log_store", default=None)


def safe_name(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.<>-]", "_", value)[:100]


def exception_chain(exc: BaseException | None) -> list[dict]:
    """Allowlisted diagnostics: never serialize messages, URLs, locals, or source lines."""
    result, seen = [], set()
    while exc is not None and id(exc) not in seen and len(result) < 8:
        seen.add(id(exc))
        item: dict = {"type": safe_name(type(exc).__name__)}
        if isinstance(exc, httpx.HTTPStatusError):
            item["upstream_status"] = exc.response.status_code
        if isinstance(exc, OSError) and isinstance(exc.errno, int):
            item["errno"] = exc.errno
        frames, trace = [], exc.__traceback__
        while trace is not None:
            code = trace.tb_frame.f_code
            frames.append(
                {
                    "file": safe_name(Path(code.co_filename).name),
                    "function": safe_name(code.co_name),
                    "line": trace.tb_lineno,
                }
            )
            trace = trace.tb_next
        item["frames"] = frames[-16:]
        result.append(item)
        exc = exc.__cause__ or (None if exc.__suppress_context__ else exc.__context__)
    return result


def request_failure(request, status: int, exc: Exception | None = None) -> None:
    if status < 400 or status == 404:
        # Expected missing artwork/routes should not overwhelm actionable diagnostics.
        return
    store = active_log_store.get()
    if store is None:
        return
    route = request.scope.get("route")
    store.append(
        {
            "level": "ERROR" if status >= 500 else "WARNING",
            "source": "http",
            "request_id": request.state.request_id,
            "method": safe_name(request.method),
            "route": getattr(route, "path", "<unmatched>"),
            "status": status,
            "code": safe_name(exc.code) if isinstance(exc, DomainError) else f"HTTP_{status}",
            "message": "HTTP 请求处理失败",
            "exceptions": exception_chain(exc),
        }
    )


class DiagnosticHandler(logging.Handler):
    def __init__(self, store: ErrorLogStore):
        super().__init__(logging.WARNING)
        self.store = store

    def emit(self, record: logging.LogRecord) -> None:
        if active_log_store.get() is not self.store:
            return
        # Logging arguments and arbitrary exception messages can contain credentials.
        exc = record.exc_info[1] if record.exc_info else sys.exc_info()[1]
        self.store.append(
            {
                "level": "ERROR" if record.levelno >= logging.ERROR else "WARNING",
                "source": safe_name(record.name),
                "request_id": None,
                "code": safe_name(exc.code)
                if isinstance(exc, DomainError)
                else "APPLICATION_ERROR",
                "message": "应用报告异常；请查看异常类型与调用位置",
                "location": {
                    "file": safe_name(Path(record.pathname).name),
                    "function": safe_name(record.funcName),
                    "line": record.lineno,
                },
                "exceptions": exception_chain(exc),
            }
        )
