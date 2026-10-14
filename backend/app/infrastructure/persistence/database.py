from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    inspect,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker


class Base(DeclarativeBase):
    pass


class MediaBindingRecord(Base):
    __tablename__ = "media_bindings"

    media_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    bangumi_id: Mapped[str | None] = mapped_column(String(100))
    tmdb_id: Mapped[str | None] = mapped_column(String(100))
    preferred_title: Mapped[str | None] = mapped_column(String(500))
    content_kind: Mapped[str] = mapped_column(String(30), default="series")
    year: Mapped[int | None] = mapped_column(Integer)
    season_number: Mapped[int] = mapped_column(Integer, default=1)
    episode_offset: Mapped[int] = mapped_column(Integer, default=0)
    folder_template: Mapped[str] = mapped_column(String(500))
    filename_template: Mapped[str] = mapped_column(String(500))
    emby_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    image_url: Mapped[str | None] = mapped_column(String(2048))
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class AppSettingRecord(Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(String(2048))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class CachedResultRecord(Base):
    __tablename__ = "cached_results"

    cache_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    media_id: Mapped[str] = mapped_column(String(64), index=True)
    category: Mapped[str] = mapped_column(String(50), index=True)
    payload_json: Mapped[Any] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class AutomationFeedRecord(Base):
    __tablename__ = "automation_feeds"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    url: Mapped[str] = mapped_column(Text, unique=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(30), default="never")
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(String(500))


class AutomationSubscriptionRecord(Base):
    __tablename__ = "automation_subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    feed_id: Mapped[int] = mapped_column(ForeignKey("automation_feeds.id"), index=True)
    title: Mapped[str] = mapped_column(String(300))
    folder_name: Mapped[str] = mapped_column(String(300))
    aliases: Mapped[list[str]] = mapped_column(JSON, default=list)
    season: Mapped[int] = mapped_column(Integer, default=1)
    episode_offset: Mapped[int] = mapped_column(Integer, default=0)
    preferred_group: Mapped[str | None] = mapped_column(String(200))
    preferred_resolution: Mapped[str | None] = mapped_column(String(40))
    exclude_keywords: Mapped[list[str]] = mapped_column(JSON, default=list)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    options_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class AutomationReleaseRecord(Base):
    __tablename__ = "automation_releases"
    __table_args__ = (UniqueConstraint("feed_id", "identity", name="uq_automation_feed_identity"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    feed_id: Mapped[int] = mapped_column(ForeignKey("automation_feeds.id"), index=True)
    identity: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(1000))
    download_url: Mapped[str] = mapped_column(Text)
    parsed: Mapped[dict] = mapped_column(JSON, default=dict)
    decision: Mapped[str] = mapped_column(String(30), default="new")
    reason: Mapped[str | None] = mapped_column(String(500))
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class AutomationDownloadRecord(Base):
    __tablename__ = "automation_downloads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    release_id: Mapped[int] = mapped_column(ForeignKey("automation_releases.id"), unique=True)
    subscription_id: Mapped[int] = mapped_column(ForeignKey("automation_subscriptions.id"))
    qb_tag: Mapped[str] = mapped_column(String(80), unique=True)
    torrent_hash: Mapped[str | None] = mapped_column(String(100))
    save_path: Mapped[str] = mapped_column(String(1000))
    local_path: Mapped[str] = mapped_column(String(1000))
    state: Mapped[str] = mapped_column(String(30), default="planned")
    progress: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(String(1000))
    naming_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class AutomationFileOperationRecord(Base):
    __tablename__ = "automation_file_operations"
    __table_args__ = (
        UniqueConstraint("download_id", "source_path", name="uq_automation_file_source"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    download_id: Mapped[int] = mapped_column(ForeignKey("automation_downloads.id"), index=True)
    source_path: Mapped[str] = mapped_column(String(1000))
    target_path: Mapped[str] = mapped_column(String(1000))
    state: Mapped[str] = mapped_column(String(30), default="planned")
    error: Mapped[str | None] = mapped_column(String(1000))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class AutomationEventRecord(Base):
    __tablename__ = "automation_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(50), index=True)
    message: Mapped[str] = mapped_column(String(1000))
    feed_id: Mapped[int | None] = mapped_column(Integer)
    download_id: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class FeatureDocumentRecord(Base):
    """Small durable documents: search cache, review plans and delivery receipts."""

    __tablename__ = "feature_documents"
    key: Mapped[str] = mapped_column(String(180), primary_key=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class UserRecord(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    username: Mapped[str] = mapped_column(String(100), unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(String(20), default="viewer")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class AccessCredentialRecord(Base):
    __tablename__ = "access_credentials"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    kind: Mapped[str] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(String(100))
    secret_hash: Mapped[str] = mapped_column(String(64), unique=True)
    scope: Mapped[str] = mapped_column(String(20), default="read")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PasskeyRecord(Base):
    __tablename__ = "passkeys"
    id: Mapped[str] = mapped_column(Text, primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    public_key: Mapped[str] = mapped_column(Text)
    sign_count: Mapped[int] = mapped_column(Integer, default=0)


def create_session_factory(database_url: str) -> sessionmaker[Session]:
    engine = create_engine(
        database_url,
        connect_args={"check_same_thread": False} if database_url.startswith("sqlite") else {},
    )
    return sessionmaker(engine, expire_on_commit=False)


def initialize_database(factory: sessionmaker[Session]) -> None:
    factory.kw["bind"].connect().close()
    Base.metadata.create_all(factory.kw["bind"])
    # Additive upgrade for installations created before the subscription shelf.
    with factory.kw["bind"].begin() as connection:
        for table, column in (
            ("automation_subscriptions", "options_json"),
            ("automation_downloads", "naming_json"),
        ):
            columns = {item["name"] for item in inspect(connection).get_columns(table)}
            if column not in columns:
                connection.execute(
                    text(f"ALTER TABLE {table} ADD COLUMN {column} JSON NOT NULL DEFAULT '{{}}'")
                )
