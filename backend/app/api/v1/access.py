from typing import Literal

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, Field

from app.api.response import ok
from app.core.errors import DomainError

router = APIRouter(prefix="/auth", tags=["access"])


class Login(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=1024)


class UserCreate(Login):
    role: Literal["admin", "operator", "viewer"] = "viewer"


class UserUpdate(BaseModel):
    enabled: bool
    role: Literal["admin", "operator", "viewer"]
    password: str | None = Field(default=None, max_length=1024)


class TokenCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    scope: Literal["read", "automation", "all"] = "read"
    days: int = Field(default=90, ge=1, le=365)


def principal(request: Request):
    user = getattr(request.state, "principal", None)
    if not user or user.get("id") == "local":
        raise DomainError("LOGIN_REQUIRED", "请先创建管理员并登录", 401)
    return user


def session_response(request, response, user):
    token = request.app.state.container.access.issue(user["id"], "Web session", "all", 7, "session")
    response.set_cookie(
        "cymf_session",
        token["token"],
        httponly=True,
        samesite="strict",
        secure=request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https",
        max_age=7 * 86400,
        path="/",
    )
    response.headers["Cache-Control"] = "no-store"
    return ok(request, user)


@router.get("/status")
def status(request: Request):
    service = request.app.state.container.access
    user = getattr(request.state, "principal", None)
    return ok(
        request,
        {
            "enabled": service.enabled(),
            "user": {k: user[k] for k in ("id", "username", "role")} if user else None,
            "passkey_configured": bool(service.passkey_config()["rp_id"]),
        },
    )


@router.post("/setup")
def setup(body: Login, request: Request, response: Response):
    service = request.app.state.container.access
    service.throttle("setup:" + request.client.host)
    user = service.create_user(body.username, body.password, "admin", setup=True)
    return session_response(request, response, user)


@router.post("/login")
def login(body: Login, request: Request, response: Response):
    service = request.app.state.container.access
    service.throttle("login:" + request.client.host)
    user = service.login(body.username, body.password)
    return session_response(request, response, user)


@router.post("/logout")
def logout(request: Request, response: Response):
    user = principal(request)
    request.app.state.container.access.revoke(user["id"], user["credential_id"])
    response.delete_cookie("cymf_session", path="/")
    return ok(request, {"logged_out": True})


@router.get("/users")
def users(request: Request):
    return ok(request, request.app.state.container.access.users())


@router.post("/users")
def add_user(body: UserCreate, request: Request):
    return ok(request, request.app.state.container.access.create_user(**body.model_dump()))


@router.put("/users/{user_id}")
def update_user(user_id: str, body: UserUpdate, request: Request):
    return ok(request, request.app.state.container.access.change_user(user_id, **body.model_dump()))


@router.get("/tokens")
def tokens(request: Request):
    return ok(request, request.app.state.container.access.credentials(principal(request)["id"]))


@router.post("/tokens")
def issue_token(body: TokenCreate, request: Request, response: Response):
    user = principal(request)
    if user["kind"] != "session":
        raise DomainError("SESSION_REQUIRED", "请通过网页登录后创建令牌", 403)
    if body.scope == "all" and user["role"] != "admin":
        raise DomainError("ADMIN_REQUIRED", "只有管理员可以创建完整权限令牌", 403)
    if body.scope == "automation" and user["role"] == "viewer":
        raise DomainError("READ_ONLY_USER", "只读用户只能创建只读令牌", 403)
    response.headers["Cache-Control"] = "no-store"
    return ok(request, request.app.state.container.access.issue(user["id"], **body.model_dump()))


@router.delete("/tokens/{token_id}")
def revoke(token_id: str, request: Request):
    request.app.state.container.access.revoke(principal(request)["id"], token_id)
    return ok(request, {"revoked": True})


class PasskeyOrigin(BaseModel):
    origin: str = Field(max_length=2048)


@router.get("/passkeys/config")
def passkey_config(request: Request):
    return ok(request, request.app.state.container.access.passkey_config())


@router.put("/passkeys/config")
def save_passkey_config(body: PasskeyOrigin, request: Request):
    return ok(request, request.app.state.container.access.save_passkey_config(body.origin))


@router.get("/passkeys")
def passkeys(request: Request):
    return ok(request, request.app.state.container.access.passkeys(principal(request)["id"]))


@router.post("/passkeys/register/options")
def register_options(request: Request):
    return ok(request, request.app.state.container.access.passkey_options(principal(request)))


@router.post("/passkeys/login/options")
def login_options(request: Request):
    service = request.app.state.container.access
    service.throttle("passkey:" + request.client.host)
    return ok(request, service.passkey_options(None))


class PasskeyVerify(BaseModel):
    challenge_id: str = Field(max_length=100)
    credential: dict
    name: str = Field(default="Passkey", max_length=100)


@router.post("/passkeys/register/verify")
def verify_registration(body: PasskeyVerify, request: Request):
    result = request.app.state.container.access.verify_passkey(
        **body.model_dump(), user=principal(request)
    )
    return ok(request, result)


@router.post("/passkeys/login/verify")
def verify_login(body: PasskeyVerify, request: Request, response: Response):
    result = request.app.state.container.access.verify_passkey(**body.model_dump())
    return session_response(request, response, result)


@router.delete("/passkeys/{key_id}")
def delete_passkey(key_id: str, request: Request):
    request.app.state.container.access.remove_passkey(principal(request)["id"], key_id)
    return ok(request, {"deleted": True})
