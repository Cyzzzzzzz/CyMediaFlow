from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select

from app.infrastructure.persistence.database import FeatureDocumentRecord


class FeatureRepository:
    def __init__(self, factory):
        self.factory = factory

    def get(self, key: str, default=None):
        with self.factory() as session:
            record = session.get(FeatureDocumentRecord, key)
            return record.payload if record else default

    def put(self, key: str, payload: dict) -> dict:
        with self.factory() as session:
            record = session.get(FeatureDocumentRecord, key)
            if record is None:
                record = FeatureDocumentRecord(key=key)
                session.add(record)
            record.payload = payload
            record.updated_at = datetime.now(timezone.utc)
            session.commit()
        return payload

    def remove(self, key: str) -> None:
        with self.factory() as session:
            record = session.get(FeatureDocumentRecord, key)
            if record:
                session.delete(record)
                session.commit()

    def prefix(self, prefix: str) -> list[dict]:
        with self.factory() as session:
            rows = session.scalars(
                select(FeatureDocumentRecord)
                .where(FeatureDocumentRecord.key.startswith(prefix, autoescape=True))
                .order_by(FeatureDocumentRecord.updated_at.desc())
            )
            return [{"key": row.key, "payload": row.payload} for row in rows]
