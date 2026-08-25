from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Integer, String, create_engine
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


def create_session_factory(database_url: str) -> sessionmaker[Session]:
    engine = create_engine(
        database_url,
        connect_args={"check_same_thread": False} if database_url.startswith("sqlite") else {},
    )
    return sessionmaker(engine, expire_on_commit=False)


def initialize_database(factory: sessionmaker[Session]) -> None:
    factory.kw["bind"].connect().close()
    Base.metadata.create_all(factory.kw["bind"])
