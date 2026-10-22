
"""
SQLite outbox retention maintenance.

Deletes only Kafka-acknowledged events older than the retention period.

Pending events are never deleted by this job.
Intended to run periodically using a systemd timer.
"""

import argparse
import logging
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "gateway" / "data" / "sensor_events.db"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("greenhouse.cleanup")


def cleanup(conn, retention_hours=24, batch_size=1000, dry_run=False):
    """Remove old delivered records in bounded transactions."""
    if retention_hours <= 0 or batch_size <= 0:
        raise ValueError("Retention and batch size must be positive")

    cutoff = (
        datetime.now(timezone.utc)
        - timedelta(hours=retention_hours)
    ).strftime("%Y-%m-%dT%H:%M:%S")

    total_deleted = 0

    if dry_run:
        count = conn.execute(
            """
            SELECT COUNT(*)
            FROM sensor_events
            WHERE kafka_published_at IS NOT NULL
              AND kafka_published_at < ?
            """,
            (cutoff,),
        ).fetchone()[0]

        logger.info("DRY RUN: %s rows eligible for deletion", count)
        return count

    while True:
        with conn:
            cursor = conn.execute(
                """
                DELETE FROM sensor_events
                WHERE event_id IN (
                    SELECT event_id
                    FROM sensor_events
                    WHERE kafka_published_at IS NOT NULL
                      AND kafka_published_at < ?
                    LIMIT ?
                )
                """,
                (cutoff, batch_size),
            )
            deleted = cursor.rowcount

        total_deleted += deleted

        if deleted < batch_size:
            break

    logger.info(
        "Cleanup completed; deleted=%s retention_hours=%s",
        total_deleted,
        retention_hours,
    )
    return total_deleted


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--retention-hours", type=int, default=24)
    parser.add_argument("--batch-size", type=int, default=1000)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not DB_PATH.exists():
        raise FileNotFoundError(f"SQLite database not found: {DB_PATH}")

    with closing(sqlite3.connect(DB_PATH, timeout=30)) as conn:
        conn.execute("PRAGMA busy_timeout = 30000")
        cleanup(
            conn,
            retention_hours=args.retention_hours,
            batch_size=args.batch_size,
            dry_run=args.dry_run,
        )


if __name__ == "__main__":
    main()
