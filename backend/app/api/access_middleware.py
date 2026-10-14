from urllib.parse import urlsplit

from fastapi.responses import JSONResponse

from app.api.response import failed

PUBLIC = {
    "/api/v1/system/health",
    "/api/v1/auth/status",
    "/api/v1/auth/login",
    "/api/v1/auth/setup",
    "/api/v1/auth/passkeys/login/options",
    "/api/v1/auth/passkeys/login/verify",
}
PERSONAL = ("/api/v1/auth/tokens", "/api/v1/auth/passkeys", "/api/v1/auth/logout")


async def access_middleware(request, call_next):
    if not request.url.path.startswith("/api/"):
        return await call_next(request)
    service = request.app.state.container.access
    bearer = request.headers.get("Authorization", "")
    token = bearer[7:] if bearer.startswith("Bearer ") else request.cookies.get("cymf_session", "")
    user = service.authenticate(token)
    request.state.principal = user
    path = request.url.path
    write = request.method not in {"GET", "HEAD", "OPTIONS"}

    def reject(code, message, status=403):
        return JSONResponse(failed(request, code, message), status_code=status)

    if write and request.headers.get("Origin"):
        origin = request.headers["Origin"].rstrip("/")
        configured = service.passkey_config()["origin"]
        if urlsplit(origin).netloc != request.headers.get("host") and origin != configured:
            return reject("ORIGIN_REJECTED", "请求来源与网站地址不一致")
    if path in PUBLIC or request.method == "OPTIONS":
        return await call_next(request)
    if not service.enabled():
        if path.startswith("/api/v1/auth/"):
            return reject("SETUP_REQUIRED", "请先创建管理员", 401)
        return await call_next(request)
    if not user:
        return reject("LOGIN_REQUIRED", "请登录 CyMediaFlow", 401)
    admin_path = (
        ("/settings" in path and (write or path == "/api/v1/settings"))
        or path.startswith("/api/v1/auth/users")
        or path == "/api/v1/auth/passkeys/config"
    )
    if admin_path and (user["role"] != "admin" or user["scope"] != "all"):
        return reject("ADMIN_REQUIRED", "此操作需要管理员权限")
    personal = path.startswith(PERSONAL)
    if personal and user["kind"] != "session":
        return reject("SESSION_REQUIRED", "账号和凭据管理需要网页登录")
    if write and not personal:
        if (user["role"] == "viewer" or user["scope"] == "read") and path not in {
            "/api/v1/mcp",
            "/api/v1/automation/notifications/read",
        }:
            return reject("READ_ONLY", "当前账号或令牌为只读权限")
        if user["scope"] == "automation" and not path.startswith(
            ("/api/v1/automation/", "/api/v1/mcp")
        ):
            return reject("TOKEN_SCOPE", "令牌仅允许自动追番操作")
    return await call_next(request)
