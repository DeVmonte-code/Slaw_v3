"""SQLite persistence for the scheduled-sweep layer (Task #22).

Why SQLite (not Postgres):

* The scope is single-process: APScheduler runs in the same uvicorn
  worker as ``/scan``, so we don't need a network DB to serialise
  writes between processes.
* Row volume is bounded: ``users`` * ``sweep_retention_per_user``
  scans + a small alerts table. Even at 10k users * 30 scans this is
  tens of MB, well inside SQLite's comfort zone.
* The only multi-writer concern is the API's ``POST /profile`` racing
  with the scheduler; SQLite's WAL mode + a single-write connection
  gives us atomic upserts without a server.

If we ever outgrow this, the surface area is intentionally narrow —
every caller goes through the module-level helpers below — so swapping
the backing store is a single-file change.

Concurrency model:
* One module-level connection, opened lazily on first use.
* ``check_same_thread=False`` so the FastAPI threadpool, the
  APScheduler thread, and pytest's main thread can all share it.
* Writes are serialised by SQLite's per-connection lock; reads are
  cheap and concurrent. Long scans run *outside* a DB transaction so a
  slow Claude call cannot block ``POST /profile``.

Test injection:
* :func:`set_db_path` lets the test suite point storage at a tmp
  file or ``:memory:`` between tests, and :func:`reset_for_tests`
  drops the connection so the next call rebuilds the schema from
  scratch.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .config import settings
from .schemas import (
    Alert,
    AlertPayload,
    BenefitReport,
    ContextProfile,
    UserRecord,
)

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_conn: sqlite3.Connection | None = None
_db_path_override: str | None = None


def _now_iso() -> str:
    """UTC ISO-8601 with a trailing ``Z`` — same shape as BenefitReport."""
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def set_db_path(path: str | Path) -> None:
    """Override the configured DB path. Used by tests."""
    global _db_path_override
    _db_path_override = str(path)
    reset_for_tests()


def reset_for_tests() -> None:
    """Drop the cached connection so the next call rebuilds the schema."""
    global _conn
    with _lock:
        if _conn is not None:
            _conn.close()
        _conn = None


def _resolve_db_path() -> str:
    raw = _db_path_override or settings.sweep_db_path
    if raw == ":memory:":
        return raw
    p = Path(raw)
    if not p.is_absolute():
        # Resolve relative to the backend package root so the API and
        # the CLI agree on where the DB lives regardless of CWD.
        p = Path(__file__).resolve().parents[2] / p
    p.parent.mkdir(parents=True, exist_ok=True)
    return str(p)


def _get_conn() -> sqlite3.Connection:
    global _conn
    with _lock:
        if _conn is None:
            path = _resolve_db_path()
            _conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
            _conn.row_factory = sqlite3.Row
            _conn.execute("PRAGMA foreign_keys = ON")
            if path != ":memory:":
                _conn.execute("PRAGMA journal_mode = WAL")
            _init_schema(_conn)
            logger.info("sweep storage initialized path=%s", path)
        return _conn


def _init_schema(conn: sqlite3.Connection) -> None:
    """Create tables idempotently. Schema is small enough to inline."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            user_id        TEXT PRIMARY KEY,
            profile_json   TEXT NOT NULL,
            notify_enabled INTEGER NOT NULL DEFAULT 1,
            created_at     TEXT NOT NULL,
            last_seen_at   TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS scan_results (
            user_id   TEXT NOT NULL,
            scan_at   TEXT NOT NULL,
            report_json TEXT NOT NULL,
            PRIMARY KEY (user_id, scan_at),
            FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_scan_results_user_scan_at
            ON scan_results(user_id, scan_at DESC);

        CREATE TABLE IF NOT EXISTS alerts (
            alert_id       TEXT PRIMARY KEY,
            user_id        TEXT NOT NULL,
            kind           TEXT NOT NULL,
            entitlement_id TEXT NOT NULL,
            created_at     TEXT NOT NULL,
            read_at        TEXT,
            payload_json   TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_alerts_user_created
            ON alerts(user_id, created_at DESC);
        """
    )


def _profile_json_for_storage(profile: ContextProfile) -> str:
    """Serialize profiles without scan-only free text."""
    payload = profile.model_copy(update={"personal_note": None})
    return payload.model_dump_json()


@contextmanager
def _txn() -> Iterator[sqlite3.Connection]:
    """Group a multi-statement write into one transaction."""
    conn = _get_conn()
    with _lock:
        conn.execute("BEGIN IMMEDIATE")
        try:
            yield conn
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise


# ----- Users --------------------------------------------------------------


def upsert_user(user_id: str, profile: ContextProfile, notify_enabled: bool) -> UserRecord:
    """Idempotent profile upsert.

    First write creates the row with ``created_at = last_seen_at = now``.
    Subsequent writes update ``profile_json``, ``notify_enabled`` and
    ``last_seen_at`` while preserving ``created_at``.
    """
    now = _now_iso()
    payload = _profile_json_for_storage(profile)
    with _txn() as conn:
        conn.execute(
            """
            INSERT INTO users (user_id, profile_json, notify_enabled,
                               created_at, last_seen_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                profile_json   = excluded.profile_json,
                notify_enabled = excluded.notify_enabled,
                last_seen_at   = excluded.last_seen_at
            """,
            (user_id, payload, int(notify_enabled), now, now),
        )
    rec = get_user(user_id)
    assert rec is not None  # we just wrote it
    return rec


def ensure_user_exists(user_id: str, profile: ContextProfile) -> None:
    """Create the user row if it does not already exist.

    Uses INSERT OR IGNORE so existing rows — including their ``notify_enabled``
    preference — are *never* mutated.  Call this before ``insert_scan`` to
    satisfy the FK constraint without overwriting user preferences.
    """
    now = _now_iso()
    payload = _profile_json_for_storage(profile)
    with _txn() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO users (user_id, profile_json, notify_enabled,
                                         created_at, last_seen_at)
            VALUES (?, ?, 1, ?, ?)
            """,
            (user_id, payload, now, now),
        )


def get_user(user_id: str) -> UserRecord | None:
    row = _get_conn().execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
    if row is None:
        return None
    return _row_to_user(row)


def list_users(*, only_notify_enabled: bool = False) -> list[UserRecord]:
    sql = "SELECT * FROM users"
    if only_notify_enabled:
        sql += " WHERE notify_enabled = 1"
    sql += " ORDER BY user_id"
    rows = _get_conn().execute(sql).fetchall()
    return [_row_to_user(r) for r in rows]


def _row_to_user(row: sqlite3.Row) -> UserRecord:
    return UserRecord(
        user_id=row["user_id"],
        profile=ContextProfile.model_validate_json(row["profile_json"]),
        notify_enabled=bool(row["notify_enabled"]),
        created_at=row["created_at"],
        last_seen_at=row["last_seen_at"],
    )


# ----- Scan results -------------------------------------------------------


def insert_scan(user_id: str, report: BenefitReport) -> None:
    """Persist one scan; key is ``(user_id, report.generated_at)``."""
    with _txn() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO scan_results (user_id, scan_at, report_json)
            VALUES (?, ?, ?)
            """,
            (user_id, report.generated_at, report.model_dump_json()),
        )


def latest_scan(user_id: str) -> BenefitReport | None:
    row = (
        _get_conn()
        .execute(
            """
        SELECT report_json FROM scan_results
        WHERE user_id = ?
        ORDER BY scan_at DESC LIMIT 1
        """,
            (user_id,),
        )
        .fetchone()
    )
    if row is None:
        return None
    return BenefitReport.model_validate_json(row["report_json"])


def iter_all_scans() -> Iterator[BenefitReport]:
    """Yield every persisted ``BenefitReport`` across all users.

    Used by the agent-backed audit (Task #25) so the aggregate counts
    EVERY shipped analysis, not just the latest report per user — a
    user who ran 12 scans must contribute 12 reports' worth of
    benefits, otherwise ``agent_backed_pct`` is silently distorted.

    Streams via ``cursor.fetchone()`` so a large history doesn't
    materialise the full result set in memory.
    """
    cur = _get_conn().execute("SELECT report_json FROM scan_results ORDER BY scan_at ASC")
    while True:
        row = cur.fetchone()
        if row is None:
            return
        yield BenefitReport.model_validate_json(row["report_json"])


def prune_scans(user_id: str, keep: int) -> int:
    """Delete all but the ``keep`` most-recent scans for ``user_id``.

    Returns the number of rows deleted so the caller can log retention
    activity.
    """
    if keep < 1:
        raise ValueError("keep must be >= 1")
    with _txn() as conn:
        cur = conn.execute(
            """
            DELETE FROM scan_results
            WHERE user_id = ?
              AND scan_at NOT IN (
                  SELECT scan_at FROM scan_results
                  WHERE user_id = ?
                  ORDER BY scan_at DESC
                  LIMIT ?
              )
            """,
            (user_id, user_id, keep),
        )
        return int(cur.rowcount or 0)


# ----- Alerts -------------------------------------------------------------


def insert_alert(alert: Alert) -> bool:
    """Insert the alert row. Idempotent on ``alert_id`` — returns False
    if the row already existed (e.g. the same sweep ran twice)."""
    with _txn() as conn:
        cur = conn.execute(
            """
            INSERT OR IGNORE INTO alerts
              (alert_id, user_id, kind, entitlement_id,
               created_at, read_at, payload_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                alert.alert_id,
                alert.user_id,
                alert.kind,
                alert.entitlement_id,
                alert.created_at,
                alert.read_at,
                alert.payload.model_dump_json(),
            ),
        )
        return bool(cur.rowcount)


def list_alerts(user_id: str, *, unread_only: bool = False, limit: int = 100) -> list[Alert]:
    sql = "SELECT * FROM alerts WHERE user_id = ?"
    params: list[Any] = [user_id]
    if unread_only:
        sql += " AND read_at IS NULL"
    sql += " ORDER BY created_at DESC LIMIT ?"
    params.append(int(limit))
    rows = _get_conn().execute(sql, params).fetchall()
    return [_row_to_alert(r) for r in rows]


def alert_exists(user_id: str, alert_id: str) -> bool:
    """Whether an alert with this ``alert_id`` is visible to ``user_id``.

    Used by the read endpoint to distinguish "404 — not your alert"
    from "204 — already read / now read"."""
    row = (
        _get_conn()
        .execute(
            "SELECT 1 FROM alerts WHERE alert_id = ? AND user_id = ?",
            (alert_id, user_id),
        )
        .fetchone()
    )
    return row is not None


def mark_alert_read(user_id: str, alert_id: str) -> bool:
    """Mark one alert as read for the given user. Returns True if a row
    was updated, False if the alert doesn't exist or belongs to someone
    else (the user_id check is the cheap auth shim until real auth lands).
    """
    now = _now_iso()
    with _txn() as conn:
        cur = conn.execute(
            """
            UPDATE alerts SET read_at = ?
            WHERE alert_id = ? AND user_id = ? AND read_at IS NULL
            """,
            (now, alert_id, user_id),
        )
        return bool(cur.rowcount)


def _row_to_alert(row: sqlite3.Row) -> Alert:
    return Alert(
        alert_id=row["alert_id"],
        user_id=row["user_id"],
        kind=row["kind"],
        entitlement_id=row["entitlement_id"],
        created_at=row["created_at"],
        read_at=row["read_at"],
        payload=AlertPayload.model_validate(json.loads(row["payload_json"])),
    )
