from __future__ import annotations

import asyncio

import httpx

from app.core.errors import DomainError


def rss_failure(exc: Exception) -> DomainError:
    """Classify a failed read without exposing the subscription URL or credentials."""
    details: dict[str, object] = {}
    if isinstance(exc, asyncio.TimeoutError | TimeoutError | httpx.TimeoutException):
        reason, message = "TIMEOUT", "RSS 请求超时，请稍后重试"
    elif isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        details["upstream_status"] = status
        reason, message = "HTTP_STATUS", f"RSS 站点返回 HTTP {status}，请检查源站是否可用"
    elif isinstance(exc, httpx.ProxyError):
        reason, message = "PROXY", "RSS 代理连接失败，请检查 RSS 代理服务"
    elif isinstance(exc, httpx.NetworkError | httpx.ProtocolError):
        reason, message = "CONNECTION", "RSS 连接建立或传输失败，请稍后重试"
    elif isinstance(exc, ValueError):
        reason, message = "INVALID_FEED", "RSS 内容无效、不是 RSS/Atom 或超过 2 MiB 限制"
    else:
        reason, message = "UNEXPECTED", "RSS 读取发生异常，请查看异常日志"
    return DomainError("RSS_UNAVAILABLE", message, 503, {**details, "reason": reason})
