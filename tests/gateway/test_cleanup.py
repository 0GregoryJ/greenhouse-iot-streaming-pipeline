
"""Tests for SQLite outbox retention and cleanup."""

import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from gateway.cleanup import cleanup


@pytest.fixture
def db(tmp_path):
    """Create an isolated SQLite outbox for each test.

    tmp_path is provided by pytest. No real Pi data is touched.
    """
    path = tmp_path / "sensor_events.db"
    conn = sqlite3.connect(path)

    conn.execute("""
        CREATE TABLE sensor_events (
            event_id TEXT PRIMARY KEY,
            event_json TEXT NOT NULL,
            received_at TEXT NOT NULL,
            kafka_published_at TEXT
        )
    """)
    conn.commit()

    yield conn

    conn.close()


def insert_event(conn, event_id, published_at=None):
    """Insert a synthetic event into the test database."""
    conn.execute(
        """
        INSERT INTO sensor_events
            (event_id, event_json, received_at, kafka_published_at)
        VALUES (?, ?, ?, ?)
        """,
        (
            event_id,
            "{}",
            datetime.now(timezone.utc).isoformat(),
            published_at,
        ),
    )
    conn.commit()


def timestamp_hours_ago(hours, use_z=False):
    dt = datetime.now(timezone.utc) - timedelta(hours=hours)

    if use_z:
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    return dt.isoformat()


def remaining_ids(conn):
    return {
        row[0]
        for row in conn.execute("SELECT event_id FROM sensor_events")
    }


def test_cleanup_deletes_expired_delivered_events(db):
    """Acknowledged events older than 24h should be deleted."""
    insert_event(
        db, "expired-1", timestamp_hours_ago(25)
    )
    insert_event(
        db, "expired-2", timestamp_hours_ago(48, use_z=True)
    )

    deleted = cleanup(db, retention_hours=24)

    assert deleted == 2
    assert remaining_ids(db) == set()


def test_cleanup_preserves_recent_delivered_events(db):
    """Recently acknowledged events should remain in SQLite."""
    insert_event(
        db, "recent-1", timestamp_hours_ago(2)
    )

    deleted = cleanup(db, retention_hours=24)

    assert deleted == 0
    assert remaining_ids(db) == {"recent-1"}


def test_cleanup_never_deletes_pending_events(db):
    """Even very old pending events must be preserved."""
    insert_event(db, "pending-1", published_at=None)

    deleted = cleanup(db, retention_hours=24)

    assert deleted == 0
    assert remaining_ids(db) == {"pending-1"}


def test_dry_run_does_not_delete_events(db):
    """Dry-run reports eligible rows without modifying data."""
    insert_event(
        db, "expired-1", timestamp_hours_ago(30)
    )

    eligible = cleanup(db, retention_hours=24, dry_run=True)

    assert eligible == 1
    assert remaining_ids(db) == {"expired-1"}


def test_cleanup_handles_multiple_batches(db):
    """Cleanup should continue until all expired rows are gone."""
    for i in range(5):
        insert_event(
            db, f"expired-{i}", timestamp_hours_ago(30)
        )

    deleted = cleanup(
        db,
        retention_hours=24,
        batch_size=2,
    )

    assert deleted == 5
    assert remaining_ids(db) == set()


@pytest.mark.parametrize(
    "retention_hours,batch_size",
    [
        (0, 100),
        (-1, 100),
        (24, 0),
        (24, -1),
    ],
)
def test_cleanup_rejects_invalid_configuration(
    db, retention_hours, batch_size
):
    with pytest.raises(ValueError):
        cleanup(
            db,
            retention_hours=retention_hours,
            batch_size=batch_size,
        )
