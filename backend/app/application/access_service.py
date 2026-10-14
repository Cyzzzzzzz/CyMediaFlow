from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit
from uuid import uuid4

from sqlalchemy import delete, func, select, text

from app.core.errors import DomainError
from app.infrastructure.persistence.database import (
    AccessCredentialRecord,
    FeatureDocumentRecord,
    PasskeyRecord,
    UserRecord,
)


def utc_now():
    return datetime.now(timezone.utc)


def password_hash(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1)
    return salt + ":" + digest.hex()


def user_json(user) -> dict:
    return {"id": user.id, "username": user.username, "role": user.role, "enabled": user.enabled}


class AccessService:
    def __init__(self, factory, documents):
        self.factory, self.documents = factory, documents
        self._attempts: dict[str, list[float]] = {}

    def enabled(self) -> bool:
        with self.factory() as session:
            return bool(session.scalar(select(func.count()).select_from(UserRecord)))

    def throttle(self, key: str):
        now = time.monotonic()
        self._attempts = {
            k: [t for t in ts if now - t < 300]
            for k, ts in self._attempts.items()
            if ts and now - ts[-1] < 300
        }
        attempts = self._attempts.setdefault(key, [])
        if len(attempts) >= 10:
            raise DomainError("LOGIN_RATE_LIMIT", "尝试次数过多，请五分钟后重试", 429)
        attempts.append(now)

    def create_user(self, username: str, password: str, role: str, setup: bool = False) -> dict:
        username = username.strip().casefold()
        if not username or len(password) < 12:
            raise DomainError("INVALID_USER", "用户名不能为空，密码至少 12 个字符")
        hashed = password_hash(password)
        with self.factory() as session:
            if session.get_bind().dialect.name == "sqlite":
                session.execute(text("BEGIN IMMEDIATE"))
            if setup and session.scalar(select(func.count()).select_from(UserRecord)):
                raise DomainError("SETUP_COMPLETE", "管理员已创建，请登录", 409)
            if session.scalar(select(UserRecord).where(UserRecord.username == username)):
                raise DomainError("USERNAME_EXISTS", "用户名已存在", 409)
            user = UserRecord(
                id=uuid4().hex,
                username=username,
                password_hash=hashed,
                role="admin" if setup else role,
            )
            session.add(user)
            session.commit()
            return user_json(user)

    def login(self, username: str, password: str) -> dict:
        with self.factory() as session:
            user = session.scalar(
                select(UserRecord).where(UserRecord.username == username.strip().casefold())
            )
            stored = user.password_hash if user else password_hash("unused-password")
            candidate = password_hash(password, stored.split(":")[0])
            if not user or not user.enabled or not hmac.compare_digest(candidate, stored):
                raise DomainError("LOGIN_FAILED", "用户名或密码错误", 401)
            return user_json(user)

    def issue(self, user_id: str, name: str, scope: str, days: int, kind: str = "token") -> dict:
        raw = "cymf_" + secrets.token_urlsafe(32)
        record = AccessCredentialRecord(
            id=uuid4().hex,
            user_id=user_id,
            kind=kind,
            name=name,
            secret_hash=hashlib.sha256(raw.encode()).hexdigest(),
            scope=scope,
            expires_at=utc_now() + timedelta(days=days),
        )
        with self.factory() as session:
            session.add(record)
            session.commit()
        return {
            "id": record.id,
            "token": raw,
            "expires_at": record.expires_at,
            "scope": scope,
            "name": name,
        }

    def authenticate(self, token: str) -> dict | None:
        if not token or len(token) > 200:
            return None
        with self.factory() as session:
            row = session.scalar(
                select(AccessCredentialRecord).where(
                    AccessCredentialRecord.secret_hash == hashlib.sha256(token.encode()).hexdigest()
                )
            )
            if not row or row.expires_at.replace(tzinfo=timezone.utc) <= utc_now():
                return None
            user = session.get(UserRecord, row.user_id)
            if not user or not user.enabled:
                return None
            return {
                **user_json(user),
                "credential_id": row.id,
                "kind": row.kind,
                "scope": row.scope,
            }

    def users(self):
        with self.factory() as session:
            return [user_json(u) for u in session.scalars(select(UserRecord))]

    def change_user(self, user_id: str, enabled: bool, role: str, password: str | None):
        with self.factory() as session:
            if session.get_bind().dialect.name == "sqlite":
                session.execute(text("BEGIN IMMEDIATE"))
            user = session.get(UserRecord, user_id)
            if not user:
                raise DomainError("USER_NOT_FOUND", "用户不存在", 404)
            admins = session.scalar(
                select(func.count())
                .select_from(UserRecord)
                .where(UserRecord.role == "admin", UserRecord.enabled.is_(True))
            )
            if (
                user.role == "admin"
                and user.enabled
                and admins == 1
                and (not enabled or role != "admin")
            ):
                raise DomainError("LAST_ADMIN", "必须保留至少一名启用的管理员")
            user.enabled, user.role = enabled, role
            if password:
                if len(password) < 12:
                    raise DomainError("WEAK_PASSWORD", "密码至少 12 个字符")
                user.password_hash = password_hash(password)
            session.execute(
                delete(AccessCredentialRecord).where(AccessCredentialRecord.user_id == user_id)
            )
            session.commit()
            return user_json(user)

    def credentials(self, user_id: str):
        with self.factory() as session:
            rows = session.scalars(
                select(AccessCredentialRecord).where(
                    AccessCredentialRecord.user_id == user_id,
                    AccessCredentialRecord.kind == "token",
                )
            )
            return [
                {"id": r.id, "name": r.name, "scope": r.scope, "expires_at": r.expires_at}
                for r in rows
            ]

    def revoke(self, user_id: str, credential_id: str):
        with self.factory() as session:
            session.execute(
                delete(AccessCredentialRecord).where(
                    AccessCredentialRecord.user_id == user_id,
                    AccessCredentialRecord.id == credential_id,
                )
            )
            session.commit()

    def passkey_config(self):
        return self.documents.get("access:passkey", {"origin": "", "rp_id": ""})

    def save_passkey_config(self, origin: str):
        parts = urlsplit(origin)
        if parts.scheme != "https" and not (
            parts.scheme == "http" and parts.hostname == "localhost"
        ):
            raise DomainError(
                "SECURE_ORIGIN_REQUIRED", "Passkey 需要 HTTPS 域名（localhost 可使用 HTTP）"
            )
        if (
            not parts.hostname
            or parts.username
            or parts.password
            or parts.path not in {"", "/"}
            or parts.query
            or parts.fragment
        ):
            raise DomainError(
                "INVALID_ORIGIN", "请输入网站来源地址，例如 https://media.example.com"
            )
        return self.documents.put(
            "access:passkey", {"origin": origin.rstrip("/"), "rp_id": parts.hostname}
        )

    def passkeys(self, user_id):
        with self.factory() as session:
            return [
                {"id": k.id, "name": k.name}
                for k in session.scalars(
                    select(PasskeyRecord).where(PasskeyRecord.user_id == user_id)
                )
            ]

    def remove_passkey(self, user_id, key_id):
        with self.factory() as session:
            session.execute(
                delete(PasskeyRecord).where(
                    PasskeyRecord.user_id == user_id, PasskeyRecord.id == key_id
                )
            )
            session.commit()

    def passkey_options(self, user: dict | None):
        import webauthn
        from webauthn.helpers.structs import (
            AuthenticatorSelectionCriteria,
            PublicKeyCredentialDescriptor,
            ResidentKeyRequirement,
            UserVerificationRequirement,
        )

        config = self.passkey_config()
        if not config["rp_id"]:
            raise DomainError("PASSKEY_NOT_CONFIGURED", "请先配置 Passkey 网站地址")
        if user:
            options = webauthn.generate_registration_options(
                rp_id=config["rp_id"],
                rp_name="CyMediaFlow",
                user_id=user["id"].encode(),
                user_name=user["username"],
                exclude_credentials=[
                    PublicKeyCredentialDescriptor(id=base64.urlsafe_b64decode(k["id"] + "==="))
                    for k in self.passkeys(user["id"])
                ],
                authenticator_selection=AuthenticatorSelectionCriteria(
                    resident_key=ResidentKeyRequirement.REQUIRED,
                    user_verification=UserVerificationRequirement.REQUIRED,
                ),
            )
        else:
            options = webauthn.generate_authentication_options(
                rp_id=config["rp_id"], user_verification=UserVerificationRequirement.REQUIRED
            )
        challenge_id = secrets.token_urlsafe(32)
        self.documents.put(
            "access:challenge:" + challenge_id,
            {
                "challenge": base64.b64encode(options.challenge).decode(),
                "user_id": user["id"] if user else None,
                "kind": "register" if user else "authenticate",
                "expires": time.time() + 300,
            },
        )
        import json

        return {
            "challenge_id": challenge_id,
            "options": json.loads(webauthn.options_to_json(options)),
        }

    def verify_passkey(self, challenge_id, credential, user=None, name="Passkey"):
        import webauthn

        with self.factory() as session:
            if session.get_bind().dialect.name == "sqlite":
                session.execute(text("BEGIN IMMEDIATE"))
            stored = session.get(FeatureDocumentRecord, "access:challenge:" + challenge_id)
            challenge = stored.payload if stored else None
            if stored:
                session.delete(stored)
                session.commit()
        expected_kind = "register" if user else "authenticate"
        if (
            not challenge
            or challenge["expires"] < time.time()
            or challenge["kind"] != expected_kind
            or challenge["user_id"] != (user["id"] if user else None)
        ):
            raise DomainError("INVALID_CHALLENGE", "Passkey 请求已失效，请重新开始", 401)
        config = self.passkey_config()
        options = {
            "credential": credential,
            "expected_challenge": base64.b64decode(challenge["challenge"]),
            "expected_rp_id": config["rp_id"],
            "expected_origin": config["origin"],
            "require_user_verification": True,
        }
        try:
            with self.factory() as session:
                if user:
                    result = webauthn.verify_registration_response(**options)
                    key_id = base64.urlsafe_b64encode(result.credential_id).decode().rstrip("=")
                    if session.get(PasskeyRecord, key_id):
                        raise ValueError("Credential already registered")
                    session.add(
                        PasskeyRecord(
                            id=key_id,
                            user_id=user["id"],
                            name=name,
                            public_key=base64.b64encode(result.credential_public_key).decode(),
                            sign_count=result.sign_count,
                        )
                    )
                    session.commit()
                    return user
                key = session.get(PasskeyRecord, credential.get("id", ""))
                if not key:
                    raise ValueError("Unknown credential")
                result = webauthn.verify_authentication_response(
                    **options,
                    credential_public_key=base64.b64decode(key.public_key),
                    credential_current_sign_count=key.sign_count,
                )
                account = session.get(UserRecord, key.user_id)
                if not account or not account.enabled:
                    raise ValueError("Disabled account")
                key.sign_count = result.new_sign_count
                session.commit()
                return user_json(account)
        except Exception as exc:
            raise DomainError("PASSKEY_FAILED", "Passkey 验证失败，请重新尝试", 401) from exc
