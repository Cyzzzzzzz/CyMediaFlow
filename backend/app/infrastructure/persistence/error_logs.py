from __future__ import annotations

import json
import sqlite3
import sys
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path


class ErrorLogStore:
    """Bounded diagnostic history, isolated from the application database."""

    def __init__(self, directory: Path, max_entries: int = 1000) -> None:
        self.path = directory / "errors.sqlite3"
        self.max_entries = max_entries
        self.write_failed = False
        try:
            directory.mkdir(parents=True, exist_ok=True)
            with closing(self._connect()) as db, db:
                db.execute("""CREATE TABLE IF NOT EXISTS error_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL, level TEXT NOT NULL,
                    request_id TEXT, code TEXT NOT NULL, payload TEXT NOT NULL
                )""")
                db.execute("CREATE INDEX IF NOT EXISTS log_request ON error_logs(request_id, id)")
            self.path.chmod(0o600)
        except (OSError, sqlite3.Error):
            self._failed()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path, timeout=0.2)

    def _failed(self) -> None:
        if not self.write_failed:
            sys.stderr.write("CyMediaFlow: diagnostic log storage unavailable.\n")
        self.write_failed = True

    def append(self, event: dict) -> None:
        try:
            with closing(self._connect()) as db, db:
                db.execute(
                    "INSERT INTO error_logs(created_at, level, request_id, code, payload) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (
                        datetime.now(timezone.utc).isoformat(),
                        event["level"],
                        event.get("request_id"),
                        event["code"],
                        json.dumps(event, ensure_ascii=False),
                    ),
                )
                db.execute(
                    "DELETE FROM error_logs WHERE id <= ("
                    "SELECT id FROM error_logs ORDER BY id DESC LIMIT 1 OFFSET ?)",
                    (self.max_entries,),
                )
            self.write_failed = False
        except (OSError, sqlite3.Error):
            # Diagnostics must never break a scrape or recursively log their own failure.
            self._failed()

    def list(
        self,
        *,
        limit: int = 50,
        before_id: int | None = None,
        level: str | None = None,
        request_id: str | None = None,
        code: str | None = None,
    ) -> dict:
        filters, values = [], []
        for column, value in (("level", level), ("request_id", request_id), ("code", code)):
            if value is not None:
                filters.append(f"{column} = ?")
                values.append(value)
        if before_id is not None:
            filters.append("id < ?")
            values.append(before_id)
        clause = " WHERE " + " AND ".join(filters) if filters else ""
        with closing(self._connect()) as db:
            rows = db.execute(
                "SELECT id, created_at, payload FROM error_logs"
                + clause
                + " ORDER BY id DESC LIMIT ?",
                (*values, limit + 1),
            ).fetchall()
        return {
            "items": [
                {**json.loads(row[2]), "id": row[0], "created_at": row[1]} for row in rows[:limit]
            ],
            "next_before_id": rows[limit - 1][0] if len(rows) > limit else None,
            "max_entries": self.max_entries,
            "write_failed": self.write_failed,
        }
