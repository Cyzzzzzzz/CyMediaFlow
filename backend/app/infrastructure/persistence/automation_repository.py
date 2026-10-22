from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import and_, or_, select, text
from sqlalchemy.orm import Session, sessionmaker

from app.domain.automation import normalized_title
from app.domain.automation_states import LEGACY_RENAME_PENDING_REASON
from app.infrastructure.persistence.database import (
    AutomationDownloadRecord,
    AutomationEventRecord,
    AutomationFeedRecord,
    AutomationFileOperationRecord,
    AutomationReleaseRecord,
    AutomationSubscriptionRecord,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class AutomationRepository:
    """Small transactional store; every state change is committed before external I/O."""

    def __init__(self, factory: sessionmaker[Session]) -> None:
        self._factory = factory

    def list_feeds(self) -> list[AutomationFeedRecord]:
        with self._factory() as session:
            return list(
                session.scalars(
                    select(AutomationFeedRecord)
                    .where(AutomationFeedRecord.deleted.is_(False))
                    .order_by(AutomationFeedRecord.id)
                )
            )

    def get_feed(self, feed_id: int) -> AutomationFeedRecord | None:
        with self._factory() as session:
            return session.get(AutomationFeedRecord, feed_id)

    def save_feed(self, feed_id: int | None, values: dict) -> AutomationFeedRecord:
        with self._factory() as session:
            record = session.get(AutomationFeedRecord, feed_id) if feed_id else None
            if record is None:
                record = session.scalar(
                    select(AutomationFeedRecord).where(AutomationFeedRecord.url == values["url"])
                )
                if record is None:
                    record = AutomationFeedRecord(**values)
                    session.add(record)
                elif record.deleted:
                    record.deleted = False
                    for key, value in values.items():
                        setattr(record, key, value)
                else:
                    raise ValueError("RSS 地址已存在")
            else:
                for key, value in values.items():
                    setattr(record, key, value)
            session.commit()
            session.refresh(record)
            return record

    def update_feed_status(self, feed_id: int, status: str, error: str | None) -> None:
        with self._factory() as session:
            record = session.get(AutomationFeedRecord, feed_id)
            if record is None:
                return
            record.status = status
            record.last_error = error
            record.last_checked_at = utc_now()
            session.commit()

    def list_subscriptions(self, feed_id: int | None = None) -> list[AutomationSubscriptionRecord]:
        with self._factory() as session:
            query = (
                select(AutomationSubscriptionRecord)
                .where(AutomationSubscriptionRecord.deleted.is_(False))
                .order_by(AutomationSubscriptionRecord.id)
            )
            if feed_id is not None:
                query = query.where(AutomationSubscriptionRecord.feed_id == feed_id)
            return list(session.scalars(query))

    def get_subscription(self, subscription_id: int) -> AutomationSubscriptionRecord | None:
        with self._factory() as session:
            return session.get(AutomationSubscriptionRecord, subscription_id)

    def save_subscription(
        self, subscription_id: int | None, values: dict
    ) -> AutomationSubscriptionRecord:
        with self._factory() as session:
            record = (
                session.get(AutomationSubscriptionRecord, subscription_id)
                if subscription_id
                else None
            )
            if record is None:
                record = AutomationSubscriptionRecord(**values)
                session.add(record)
            else:
                for key, value in values.items():
                    setattr(record, key, value)
            session.commit()
            session.refresh(record)
            return record

    def subscribe_feed(
        self, feed_values: dict, rules: list[dict]
    ) -> tuple[AutomationFeedRecord, list[AutomationSubscriptionRecord], int]:
        """Atomically commit source and rules; repeated confirmation is idempotent."""
        with self._factory() as session:
            if session.get_bind().dialect.name == "sqlite":
                # Serialize the read-before-insert transaction, including concurrent confirmations.
                session.execute(text("BEGIN IMMEDIATE"))
            feed = session.scalar(
                select(AutomationFeedRecord).where(AutomationFeedRecord.url == feed_values["url"])
            )
            if feed is None:
                feed = AutomationFeedRecord(**feed_values)
                session.add(feed)
                session.flush()
            elif feed.deleted:
                feed.deleted, feed.enabled = False, True
            existing = list(
                session.scalars(
                    select(AutomationSubscriptionRecord).where(
                        AutomationSubscriptionRecord.feed_id == feed.id,
                        AutomationSubscriptionRecord.deleted.is_(False),
                    )
                )
            )
            selected, created = [], 0

            def identity(values: dict) -> tuple:
                options = values.get("options_json") or {}
                return (
                    normalized_title(options.get("source_title") or values["title"]),
                    values["season"],
                    values.get("preferred_group"),
                    values.get("preferred_resolution"),
                    options.get("preferred_subtitle"),
                )

            by_identity = {
                identity(
                    {
                        "title": row.title,
                        "season": row.season,
                        "preferred_group": row.preferred_group,
                        "preferred_resolution": row.preferred_resolution,
                        "options_json": row.options_json,
                    }
                ): row
                for row in existing
            }
            for values in rules:
                key = identity(values)
                record = by_identity.get(key)
                if record is None:
                    record = AutomationSubscriptionRecord(feed_id=feed.id, **values)
                    session.add(record)
                    by_identity[key] = record
                    created += 1
                if record not in selected:
                    selected.append(record)
            session.commit()
            session.refresh(feed)
            for record in selected:
                session.refresh(record)
            return feed, selected, created

    def soft_delete_feed(self, feed_id: int) -> None:
        with self._factory() as session:
            record = session.get(AutomationFeedRecord, feed_id)
            if record is not None:
                record.deleted = True
                record.enabled = False
                for rule in session.scalars(
                    select(AutomationSubscriptionRecord).where(
                        AutomationSubscriptionRecord.feed_id == feed_id
                    )
                ):
                    rule.enabled = False
                session.commit()

    def soft_delete_subscription(self, subscription_id: int) -> None:
        with self._factory() as session:
            record = session.get(AutomationSubscriptionRecord, subscription_id)
            if record is not None:
                record.deleted = True
                record.enabled = False
                session.commit()

    def get_or_add_release(
        self, feed_id: int, identity: str, values: dict
    ) -> AutomationReleaseRecord:
        with self._factory() as session:
            record = session.scalar(
                select(AutomationReleaseRecord).where(
                    AutomationReleaseRecord.feed_id == feed_id,
                    AutomationReleaseRecord.identity == identity,
                )
            )
            if record is None:
                record = AutomationReleaseRecord(feed_id=feed_id, identity=identity, **values)
                session.add(record)
                session.commit()
                session.refresh(record)
            return record

    def set_release_decision(self, release_id: int, decision: str, reason: str | None) -> None:
        with self._factory() as session:
            record = session.get(AutomationReleaseRecord, release_id)
            if record is not None:
                record.decision, record.reason = decision, reason
                session.commit()

    def get_release(self, release_id: int) -> AutomationReleaseRecord | None:
        with self._factory() as session:
            return session.get(AutomationReleaseRecord, release_id)

    def list_releases(
        self, feed_id: int | None = None, limit: int = 100
    ) -> list[AutomationReleaseRecord]:
        with self._factory() as session:
            query = (
                select(AutomationReleaseRecord)
                .order_by(AutomationReleaseRecord.id.desc())
                .limit(limit)
            )
            if feed_id is not None:
                query = query.where(AutomationReleaseRecord.feed_id == feed_id)
            return list(session.scalars(query))

    def get_download_by_release(self, release_id: int) -> AutomationDownloadRecord | None:
        with self._factory() as session:
            return session.scalar(
                select(AutomationDownloadRecord).where(
                    AutomationDownloadRecord.release_id == release_id
                )
            )

    def get_download(self, download_id: int) -> AutomationDownloadRecord | None:
        with self._factory() as session:
            return session.get(AutomationDownloadRecord, download_id)

    def create_download(
        self,
        release_id: int,
        subscription_id: int,
        save_path: str,
        local_path: str,
        naming: dict | None = None,
    ) -> AutomationDownloadRecord:
        with self._factory() as session:
            record = AutomationDownloadRecord(
                release_id=release_id,
                subscription_id=subscription_id,
                qb_tag=f"cymf-{release_id}",
                save_path=save_path,
                local_path=local_path,
                naming_json=naming or {},
            )
            session.add(record)
            session.commit()
            session.refresh(record)
            return record

    def list_downloads(self, limit: int = 100) -> list[AutomationDownloadRecord]:
        with self._factory() as session:
            return list(
                session.scalars(
                    select(AutomationDownloadRecord)
                    .order_by(AutomationDownloadRecord.id.desc())
                    .limit(limit)
                )
            )

    def list_pending_downloads(self) -> list[AutomationDownloadRecord]:
        # Only this precise legacy error is recoverable without human approval.
        # A persisted plan is required; restored names must never be changed back.
        legacy_rename = and_(
            AutomationDownloadRecord.state == "review",
            AutomationDownloadRecord.error == LEGACY_RENAME_PENDING_REASON,
            AutomationDownloadRecord.torrent_hash.is_not(None),
            AutomationDownloadRecord.progress == 100,
            select(AutomationFileOperationRecord.id)
            .where(
                AutomationFileOperationRecord.download_id == AutomationDownloadRecord.id,
                AutomationFileOperationRecord.state.in_(("running", "done")),
            )
            .exists(),
            ~select(AutomationFileOperationRecord.id)
            .where(
                AutomationFileOperationRecord.download_id == AutomationDownloadRecord.id,
                AutomationFileOperationRecord.state == "restored",
            )
            .exists(),
        )
        stale_completed_release = and_(
            AutomationDownloadRecord.state.in_(("organized", "revision_ready")),
            select(AutomationReleaseRecord.id)
            .where(
                AutomationReleaseRecord.id == AutomationDownloadRecord.release_id,
                AutomationReleaseRecord.decision == "review",
                AutomationReleaseRecord.reason == LEGACY_RENAME_PENDING_REASON,
            )
            .exists(),
        )
        with self._factory() as session:
            return list(
                session.scalars(
                    select(AutomationDownloadRecord)
                    .where(
                        or_(
                            AutomationDownloadRecord.state.not_in(
                                (
                                    "organized",
                                    "review",
                                    "removed",
                                    "superseded",
                                    "downloaded",
                                    "revision_ready",
                                )
                            ),
                            legacy_rename,
                            stale_completed_release,
                        )
                    )
                    .order_by(AutomationDownloadRecord.id)
                )
            )

    def update_download(self, download_id: int, **values: object) -> None:
        with self._factory() as session:
            record = session.get(AutomationDownloadRecord, download_id)
            if record is None:
                return
            for key, value in values.items():
                setattr(record, key, value)
            record.updated_at = utc_now()
            session.commit()

    def set_download_outcome(
        self, download_id: int, state: str, decision: str, reason: str | None = None
    ) -> None:
        """Commit task and candidate together, without undoing an explicit exclusion."""
        with self._factory() as session:
            job = session.get(AutomationDownloadRecord, download_id)
            if job is None:
                return
            job.state, job.error, job.updated_at = state, reason, utc_now()
            release = session.get(AutomationReleaseRecord, job.release_id)
            if release is not None and release.decision != "excluded":
                release.decision, release.reason = decision, reason
            session.commit()

    def list_operations(self, download_id: int) -> list[AutomationFileOperationRecord]:
        with self._factory() as session:
            return list(
                session.scalars(
                    select(AutomationFileOperationRecord)
                    .where(AutomationFileOperationRecord.download_id == download_id)
                    .order_by(AutomationFileOperationRecord.id)
                )
            )

    def plan_operation(
        self, download_id: int, source: str, target: str
    ) -> AutomationFileOperationRecord:
        with self._factory() as session:
            record = session.scalar(
                select(AutomationFileOperationRecord).where(
                    AutomationFileOperationRecord.download_id == download_id,
                    AutomationFileOperationRecord.source_path == source,
                )
            )
            if record is None:
                record = AutomationFileOperationRecord(
                    download_id=download_id,
                    source_path=source,
                    target_path=target,
                )
                session.add(record)
                session.commit()
                session.refresh(record)
            return record

    def plan_operations(self, download_id: int, files: list[dict]) -> None:
        """Commit the whole plan before the first filesystem/downloader mutation."""
        with self._factory() as session:
            existing = session.scalar(
                select(AutomationFileOperationRecord.id)
                .where(AutomationFileOperationRecord.download_id == download_id)
                .limit(1)
            )
            if existing is not None:
                raise ValueError("整理计划已存在，请刷新状态")
            session.add_all(
                [
                    AutomationFileOperationRecord(
                        download_id=download_id,
                        source_path=row["source"],
                        target_path=row["target"],
                    )
                    for row in files
                ]
            )
            session.commit()

    def update_operation(self, operation_id: int, state: str, error: str | None = None) -> None:
        with self._factory() as session:
            record = session.get(AutomationFileOperationRecord, operation_id)
            if record is None:
                return
            record.state, record.error, record.updated_at = state, error, utc_now()
            session.commit()

    def add_event(
        self, kind: str, message: str, *, feed_id: int | None = None, download_id: int | None = None
    ) -> None:
        with self._factory() as session:
            session.add(
                AutomationEventRecord(
                    kind=kind,
                    message=message[:1000],
                    feed_id=feed_id,
                    download_id=download_id,
                )
            )
            session.commit()

    def list_events(self, limit: int = 100) -> list[AutomationEventRecord]:
        with self._factory() as session:
            return list(
                session.scalars(
                    select(AutomationEventRecord)
                    .order_by(AutomationEventRecord.id.desc())
                    .limit(limit)
                )
            )

    def events_after(self, after: int, limit: int = 100) -> list[AutomationEventRecord]:
        with self._factory() as session:
            return list(
                session.scalars(
                    select(AutomationEventRecord)
                    .where(AutomationEventRecord.id > after)
                    .order_by(AutomationEventRecord.id)
                    .limit(limit)
                )
            )

    def update_release_analysis(self, release_id: int, parsed: dict) -> None:
        with self._factory() as session:
            record = session.get(AutomationReleaseRecord, release_id)
            if record:
                record.parsed = parsed
                session.commit()
