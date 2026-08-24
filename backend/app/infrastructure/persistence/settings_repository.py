from __future__ import annotations

from sqlalchemy.orm import Session, sessionmaker

from app.infrastructure.persistence.database import AppSettingRecord


class SqlAlchemySettingsRepository:
    def __init__(self, factory: sessionmaker[Session]) -> None:
        self._factory = factory

    def get(self, key: str) -> str | None:
        with self._factory() as session:
            record = session.get(AppSettingRecord, key)
            return record.value if record else None

    def set(self, key: str, value: str) -> None:
        with self._factory() as session:
            record = session.get(AppSettingRecord, key)
            if record is None:
                record = AppSettingRecord(key=key, value=value)
                session.add(record)
            else:
                record.value = value
            session.commit()
