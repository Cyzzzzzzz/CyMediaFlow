from __future__ import annotations

from sqlalchemy.orm import Session, sessionmaker

from app.domain.media import ScrapeBinding
from app.infrastructure.persistence.database import MediaBindingRecord


class SqlAlchemyBindingRepository:
    def __init__(self, factory: sessionmaker[Session]) -> None:
        self._factory = factory

    def get(self, media_id: str) -> ScrapeBinding | None:
        with self._factory() as session:
            record = session.get(MediaBindingRecord, media_id)
            return self._to_domain(record) if record else None

    def list_all(self) -> dict[str, ScrapeBinding]:
        with self._factory() as session:
            records = session.query(MediaBindingRecord).all()
            return {record.media_id: self._to_domain(record) for record in records}

    def upsert(self, binding: ScrapeBinding) -> ScrapeBinding:
        with self._factory.begin() as session:
            record = session.get(MediaBindingRecord, binding.media_id)
            if record is None:
                record = MediaBindingRecord(media_id=binding.media_id)
                session.add(record)
            record.bangumi_id = binding.bangumi_id
            record.tmdb_id = binding.tmdb_id
            record.preferred_title = binding.preferred_title
            record.content_kind = binding.content_kind
            record.year = binding.year
            record.season_number = binding.season_number
            record.episode_offset = binding.episode_offset
            record.folder_template = binding.folder_template
            record.filename_template = binding.filename_template
            record.emby_enabled = binding.emby_enabled
            record.image_url = binding.image_url
            record.metadata_json = binding.metadata
        return binding

    @staticmethod
    def _to_domain(record: MediaBindingRecord) -> ScrapeBinding:
        return ScrapeBinding(
            media_id=record.media_id,
            bangumi_id=record.bangumi_id,
            tmdb_id=record.tmdb_id,
            preferred_title=record.preferred_title,
            content_kind=record.content_kind,
            year=record.year,
            season_number=record.season_number,
            episode_offset=record.episode_offset,
            folder_template=record.folder_template,
            filename_template=record.filename_template,
            emby_enabled=record.emby_enabled,
            image_url=record.image_url,
            metadata=record.metadata_json or {},
        )
