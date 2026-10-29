
"""
Read-only health monitor for the Raspberry Pi greenhouse gateway.

Checks:
- MQTT ingestion freshness (based on the latest SQLite record)
- Kafka publishing backlog and delivery freshness
- SQLite database size and available disk space

Outputs one JSON object per invocation.

Exit codes:
    0: healthy
    1: warning (degraded or insufficient information)
    2: critical (action required)

Intended to periodically on the Raspberry Pi gateway using a systemd timer.
"""

import argparse
import json
import logging
import shutil
import sqlite3
import sys
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "gateway" / "data" / "sensor_events.db"

logger = logging.getLogger("greenhouse.health")


def parse_timestamp(value):
    """Parse gateway UTC timestamps, accepting Z and +00:00 formats."""
    if value is None:
        return None

    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))

    if parsed.tzinfo is None:
        raise ValueError(f"Naive timestamp: {value}")

    return parsed.astimezone(timezone.utc)


def age_seconds(value, now):
    """Return age in seconds, or None when no timestamp is available."""
    parsed = parse_timestamp(value)

    if parsed is None:
        return None

    return max(0.0, (now - parsed).total_seconds())


def collect_metrics(db_path, now):
    """Read gateway metrics without modifying the database."""
    if not db_path.is_file():
        raise FileNotFoundError(f"SQLite database not found: {db_path}")

    # Read-only URI prevents accidentally creating or writing a database.
    db_uri = db_path.resolve().as_uri() + "?mode=ro"

    with closing(sqlite3.connect(db_uri, uri=True, timeout=5)) as conn:
        conn.execute("PRAGMA busy_timeout = 5000")

        row = conn.execute(
            """
            SELECT
                COUNT(*) AS total_events,
                COUNT(*) FILTER (
                    WHERE kafka_published_at IS NULL
                ) AS pending_events,
                MIN(received_at) FILTER (
                    WHERE kafka_published_at IS NULL
                ) AS oldest_pending_at,
                MAX(received_at) AS latest_received_at,
                MAX(kafka_published_at) AS latest_delivered_at
            FROM sensor_events
            """
        ).fetchone()

    total, pending, oldest_pending, latest_received, latest_delivered = row

    # sqlite_db_bytes reports only the main database file.
    disk = shutil.disk_usage(db_path.parent)

    return {
        "total_events": total,
        "pending_events": pending,
        "oldest_pending_at": oldest_pending,
        "oldest_pending_age_seconds": age_seconds(oldest_pending, now),
        "latest_received_at": latest_received,
        "latest_received_age_seconds": age_seconds(latest_received, now),
        "latest_delivered_at": latest_delivered,
        "latest_delivered_age_seconds": age_seconds(latest_delivered, now),
        "sqlite_db_bytes": db_path.stat().st_size,
        "disk_total_bytes": disk.total,
        "disk_free_bytes": disk.free,
        "disk_used_percent": round(
            100 * disk.used / disk.total, 2
        ),
    }


def evaluate_health(metrics, args):
    """Classify observations into healthy, warning, or critical."""
    warnings = []
    critical = []

    received_age = metrics["latest_received_age_seconds"]
    pending_age = metrics["oldest_pending_age_seconds"]
    pending_count = metrics["pending_events"]
    disk_used = metrics["disk_used_percent"]

    # A monitoring script cannot automatically distinguish intentional
    # simulator shutdown from a genuine ingestion outage.
    if received_age is None:
        warnings.append("No sensor readings stored")
    elif received_age > args.ingest_stale_seconds:
        warnings.append(
            f"Ingestion stale: latest event {received_age:.0f}s ago"
        )

    if pending_age is not None:
        if pending_age > args.pending_critical_seconds:
            critical.append(
                f"Oldest pending event is {pending_age:.0f}s old"
            )
        elif pending_age > args.pending_warn_seconds:
            warnings.append(
                f"Kafka backlog age is {pending_age:.0f}s"
            )

    if pending_count >= args.pending_critical_count:
        critical.append(
            f"Kafka backlog contains {pending_count} events"
        )
    elif pending_count >= args.pending_warn_count:
        warnings.append(
            f"Kafka backlog contains {pending_count} events"
        )

    if disk_used >= args.disk_critical_percent:
        critical.append(f"Disk utilization is {disk_used}%")
    elif disk_used >= args.disk_warn_percent:
        warnings.append(f"Disk utilization is {disk_used}%")

    # Do not flag old Kafka delivery timestamps if there are no
    # undelivered events: the simulator might simply be stopped.
    if pending_count > 0 and metrics["latest_delivered_at"] is None:
        warnings.append("No Kafka delivery recorded in local outbox")

    if critical:
        status = "critical"
        exit_code = 2
    elif warnings:
        status = "warning"
        exit_code = 1
    else:
        status = "healthy"
        exit_code = 0

    return status, warnings + critical, exit_code


def main():
    parser = argparse.ArgumentParser(
        description="Monitor the greenhouse gateway"
    )
    parser.add_argument(
        "--ingest-stale-seconds", type=int, default=120
    )
    parser.add_argument(
        "--pending-warn-seconds", type=int, default=60
    )
    parser.add_argument(
        "--pending-critical-seconds", type=int, default=300
    )
    parser.add_argument(
        "--pending-warn-count", type=int, default=1000
    )
    parser.add_argument(
        "--pending-critical-count", type=int, default=10000
    )
    parser.add_argument(
        "--disk-warn-percent", type=float, default=80.0
    )
    parser.add_argument(
        "--disk-critical-percent", type=float, default=90.0
    )
    parser.add_argument(
        "--db-path", type=Path, default=DB_PATH
    )
    args = parser.parse_args()

    now = datetime.now(timezone.utc)

    try:
        metrics = collect_metrics(args.db_path, now)
        status, issues, exit_code = evaluate_health(metrics, args)

        result = {
            "timestamp": now.isoformat(),
            "gateway_id": "pi-001",
            "status": status,
            "issues": issues,
            "metrics": metrics,
        }

    except (OSError, sqlite3.Error, ValueError) as exc:
        logger.exception("Health check failed")
        result = {
            "timestamp": now.isoformat(),
            "gateway_id": "pi-001",
            "status": "critical",
            "issues": [f"Unable to inspect gateway: {exc}"],
            "metrics": {},
        }
        exit_code = 2

    print(json.dumps(result, indent=2))
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
