from __future__ import annotations

from datetime import time

from sqlalchemy.orm import Session, sessionmaker

from app.domain.media import (
    EpisodeSourceRule,
    ProviderSubjectBinding,
    ScheduledRefresh,
    ScrapeBinding,
    normalize_primary_binding,
)
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
        binding = normalize_primary_binding(binding)
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
            metadata = dict(binding.metadata)
            metadata["provider_subjects"] = [
                {
                    "provider": subject.provider,
                    "external_id": subject.external_id,
                    "title": subject.title,
                    "original_title": subject.original_title,
                    "image_url": subject.image_url,
                    "role": subject.role,
                }
                for subject in binding.provider_subjects
            ]
            metadata["episode_source_rules"] = [
                {
                    "provider": rule.provider,
                    "external_id": rule.external_id,
                    "local_season": rule.local_season,
                    "local_episode_start": rule.local_episode_start,
                    "local_episode_end": rule.local_episode_end,
                    "provider_episode_start": rule.provider_episode_start,
                    "provider_season": rule.provider_season,
                    "number_mode": rule.number_mode,
                    "local_path": rule.local_path,
                }
                for rule in binding.episode_source_rules
            ]
            metadata["scheduled_refresh"] = {
                "enabled": binding.scheduled_refresh.enabled,
                "daily_time": binding.scheduled_refresh.daily_time,
                "last_run_at": binding.scheduled_refresh.last_run_at,
                "last_status": binding.scheduled_refresh.last_status,
                "last_message": binding.scheduled_refresh.last_message,
                "current_episode": binding.scheduled_refresh.current_episode,
                "total_episodes": binding.scheduled_refresh.total_episodes,
                "final_air_date": binding.scheduled_refresh.final_air_date,
            }
            record.metadata_json = metadata
        return binding

    @staticmethod
    def _to_domain(record: MediaBindingRecord) -> ScrapeBinding:
        metadata = dict(record.metadata_json or {})
        subjects = SqlAlchemyBindingRepository._subjects_from_json(
            metadata.pop("provider_subjects", None)
        )
        rules = SqlAlchemyBindingRepository._rules_from_json(
            metadata.pop("episode_source_rules", None)
        )
        scheduled_refresh = SqlAlchemyBindingRepository._scheduled_refresh_from_json(
            metadata.pop("scheduled_refresh", None)
        )
        if not subjects:
            subjects = SqlAlchemyBindingRepository._legacy_subjects(record, metadata)
        return normalize_primary_binding(ScrapeBinding(
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
            metadata=metadata,
            provider_subjects=subjects,
            episode_source_rules=rules,
            scheduled_refresh=scheduled_refresh,
        ))

    @staticmethod
    def _scheduled_refresh_from_json(value: object) -> ScheduledRefresh:
        if not isinstance(value, dict):
            return ScheduledRefresh()
        daily_time = SqlAlchemyBindingRepository._daily_time(value.get("daily_time"))
        last_status = value.get("last_status")
        return ScheduledRefresh(
            enabled=value.get("enabled") is True,
            daily_time=daily_time,
            last_run_at=SqlAlchemyBindingRepository._optional_text(
                value.get("last_run_at")
            ),
            last_status=(
                last_status
                if last_status in {"never", "success", "failed", "completed"}
                else "never"
            ),
            last_message=SqlAlchemyBindingRepository._optional_text(
                value.get("last_message")
            ),
            current_episode=SqlAlchemyBindingRepository._optional_int(
                value.get("current_episode")
            ),
            total_episodes=SqlAlchemyBindingRepository._optional_int(
                value.get("total_episodes")
            ),
            final_air_date=SqlAlchemyBindingRepository._optional_text(
                value.get("final_air_date")
            ),
        )

    @staticmethod
    def _optional_text(value: object) -> str | None:
        return value if isinstance(value, str) and value else None

    @staticmethod
    def _optional_int(value: object) -> int | None:
        return value if isinstance(value, int) and not isinstance(value, bool) else None

    @staticmethod
    def _daily_time(value: object) -> str:
        if not isinstance(value, str):
            return "04:00"
        try:
            parsed = time.fromisoformat(value)
        except ValueError:
            return "04:00"
        return parsed.strftime("%H:%M")

    @staticmethod
    def _subjects_from_json(value: object) -> tuple[ProviderSubjectBinding, ...]:
        if not isinstance(value, list):
            return ()
        subjects: list[ProviderSubjectBinding] = []
        for item in value:
            if not isinstance(item, dict):
                continue
            provider = item.get("provider")
            external_id = item.get("external_id")
            title = item.get("title")
            if provider not in {"bangumi", "tmdb"} or not isinstance(external_id, str):
                continue
            subjects.append(
                ProviderSubjectBinding(
                    provider=provider,
                    external_id=external_id,
                    title=(
                        title
                        if isinstance(title, str) and title
                        else f"{provider.upper()} #{external_id}"
                    ),
                    original_title=(
                        item.get("original_title")
                        if isinstance(item.get("original_title"), str)
                        else None
                    ),
                    image_url=(
                        item.get("image_url") if isinstance(item.get("image_url"), str) else None
                    ),
                    role=(item.get("role") if isinstance(item.get("role"), str) else "season_part"),
                )
            )
        return tuple(subjects)

    @staticmethod
    def _rules_from_json(value: object) -> tuple[EpisodeSourceRule, ...]:
        if not isinstance(value, list):
            return ()
        rules: list[EpisodeSourceRule] = []
        for item in value:
            if not isinstance(item, dict):
                continue
            try:
                rules.append(
                    EpisodeSourceRule(
                        provider=str(item["provider"]),
                        external_id=str(item["external_id"]),
                        local_season=int(item["local_season"]),
                        local_episode_start=int(item["local_episode_start"]),
                        local_episode_end=(
                            int(item["local_episode_end"])
                            if item.get("local_episode_end") is not None
                            else None
                        ),
                        provider_episode_start=int(item.get("provider_episode_start", 1)),
                        provider_season=int(item.get("provider_season", 1)),
                        number_mode=str(item.get("number_mode", "episode")),
                        local_path=(
                            str(item["local_path"])
                            if item.get("local_path") is not None
                            else None
                        ),
                    )
                )
            except (KeyError, TypeError, ValueError):
                continue
        return tuple(rules)

    @staticmethod
    def _legacy_subjects(
        record: MediaBindingRecord, metadata: dict[str, object]
    ) -> tuple[ProviderSubjectBinding, ...]:
        subjects: list[ProviderSubjectBinding] = []
        for provider, external_id in (
            ("bangumi", record.bangumi_id),
            ("tmdb", record.tmdb_id),
        ):
            if not external_id:
                continue
            title = metadata.get(f"{provider}_candidate_title")
            subjects.append(
                ProviderSubjectBinding(
                    provider=provider,
                    external_id=external_id,
                    title=(
                        title
                        if isinstance(title, str) and title
                        else f"{provider.upper()} #{external_id}"
                    ),
                    original_title=(
                        metadata.get(f"{provider}_original_title")
                        if isinstance(metadata.get(f"{provider}_original_title"), str)
                        else None
                    ),
                    image_url=record.image_url,
                    role="primary",
                )
            )
        return tuple(subjects)
