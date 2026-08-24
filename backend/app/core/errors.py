from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class DomainError(Exception):
    code: str
    message: str
    status_code: int = 400
    details: dict[str, object] = field(default_factory=dict)


class MediaNotFoundError(DomainError):
    def __init__(self, media_id: str) -> None:
        super().__init__(
            code="MEDIA_NOT_FOUND",
            message="没有找到对应的媒体目录",
            status_code=404,
            details={"media_id": media_id},
        )


class ProviderUnavailableError(DomainError):
    def __init__(self, message: str) -> None:
        super().__init__(
            code="METADATA_PROVIDER_UNAVAILABLE",
            message=message,
            status_code=503,
        )


class InvalidProviderImageError(DomainError):
    def __init__(self) -> None:
        super().__init__(
            code="INVALID_PROVIDER_IMAGE_URL",
            message="不支持的元数据图片地址",
            status_code=400,
        )


class ProviderArtworkUnavailableError(DomainError):
    def __init__(self, reason: str = "PROVIDER_ARTWORK_NOT_FOUND") -> None:
        super().__init__(
            code=reason,
            message="没有可用的本地或远程元数据图片",
            status_code=404,
        )


class NfoGenerationError(DomainError):
    def __init__(self, code: str, message: str, details: dict[str, object] | None = None) -> None:
        super().__init__(
            code=code,
            message=message,
            status_code=409 if code != "NFO_WRITE_FAILED" else 500,
            details=details or {},
        )
