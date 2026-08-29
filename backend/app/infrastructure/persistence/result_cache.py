from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session, sessionmaker

from app.infrastructure.persistence.database import CachedResultRecord


class SqlAlchemyResultCache:
    """Persistent, manually refreshed cache for expensive drawer results."""

    def __init__(self, factory: sessionmaker[Session]) -> None:
        self._factory = factory

    def get(
        self,
        media_id: str,
        category: str,
        parameters: Mapping[str, object] | None = None,
    ) -> Any | None:
        cache_key = self._key(media_id, category, parameters)
        with self._factory() as session:
            record = session.get(CachedResultRecord, cache_key)
            return record.payload_json if record is not None else None

    def put(
        self,
        media_id: str,
        category: str,
        payload: object,
        parameters: Mapping[str, object] | None = None,
    ) -> None:
        cache_key = self._key(media_id, category, parameters)
        statement = insert(CachedResultRecord).values(
            cache_key=cache_key,
            media_id=media_id,
            category=category,
            payload_json=payload,
        )
        statement = statement.on_conflict_do_update(
            index_elements=[CachedResultRecord.cache_key],
            set_={
                "media_id": media_id,
                "category": category,
                "payload_json": payload,
                "updated_at": datetime.now(timezone.utc),
            },
        )
        with self._factory.begin() as session:
            session.execute(statement)

    def delete(self, media_id: str, categories: Iterable[str] | None = None) -> None:
        statement = delete(CachedResultRecord).where(CachedResultRecord.media_id == media_id)
        selected = tuple(categories or ())
        if selected:
            statement = statement.where(CachedResultRecord.category.in_(selected))
        with self._factory.begin() as session:
            session.execute(statement)

    @staticmethod
    def _key(
        media_id: str,
        category: str,
        parameters: Mapping[str, object] | None,
    ) -> str:
        canonical = json.dumps(
            {
                "media_id": media_id,
                "category": category,
                "parameters": parameters or {},
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
