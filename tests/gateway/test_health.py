
"""Tests for gateway health classification and metrics."""

import sqlite3
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from gateway.health import collect_metrics, evaluate_health


@pytest.fixture
def thresholds():
    """Match the default health-monitor thresholds."""
    return SimpleNamespace(
        ingest_stale_seconds=120,
        pending_warn_seconds=60,
        pending_critical_seconds=300,
        pending_warn_count=1000,
        pending_critical_count=10000,
        disk_warn_percent=80.0,
        disk_critical_percent=90.0,
    )


@pytest.fixture
def healthy_metrics():
    """Baseline representing a working gateway."""
    return {
        "pending_events": 0,
        "oldest_pending_age_seconds": None,
        "latest_received_age_seconds": 2,
        "latest_delivered_at": "2026-10-22T12:00:00Z",
        "disk_used_percent": 25.0,
    }


def test_healthy_gateway(healthy_metrics, thresholds):
    status, issues, code = evaluate_health(
        healthy_metrics, thresholds
    )

    assert status == "healthy"
    assert issues == []
    assert code == 0


def test_stale_ingestion_triggers_warning(
    healthy_metrics, thresholds
):
    healthy_metrics["latest_received_age_seconds"] = 180

    status, issues, code = evaluate_health(
        healthy_metrics, thresholds
    )

    assert status == "warning"
    assert code == 1
    assert any("Ingestion stale" in issue for issue in issues)


def test_old_kafka_backlog_triggers_critical(
    healthy_metrics, thresholds
):
    healthy_metrics["pending_events"] = 50
    healthy_metrics["oldest_pending_age_seconds"] = 360

    status, issues, code = evaluate_health(
        healthy_metrics, thresholds
    )

    assert status == "critical"
    assert code == 2
    assert any("Oldest pending" in issue for issue in issues)


def test_disk_usage_warning(healthy_metrics, thresholds):
    healthy_metrics["disk_used_percent"] = 85.0

    status, issues, code = evaluate_health(
        healthy_metrics, thresholds
    )

    assert status == "warning"
    assert code == 1


def test_disk_usage_critical(healthy_metrics, thresholds):
    healthy_metrics["disk_used_percent"] = 95.0

    status, issues, code = evaluate_health(
        healthy_metrics, thresholds
    )

    assert status == "critical"
    assert code == 2


def test_critical_takes_precedence_over_warning(
    healthy_metrics, thresholds
):
    healthy_metrics["latest_received_age_seconds"] = 180
    healthy_metrics["disk_used_percent"] = 95.0

    status, issues, code = evaluate_health(
        healthy_metrics, thresholds
    )

    assert status == "critical"
    assert code == 2
    assert len(issues) == 2


def test_collect_metrics_reads_temporary_database(tmp_path):
    """Integration-style test using a real temporary SQLite file."""
    db_path = tmp_path / "test.db"
    now = datetime.now(timezone.utc)

    received_at = (
        now - timedelta(seconds=10)
    ).isoformat()

    with sqlite3.connect(db_path) as conn:
        conn.execute("""
            CREATE TABLE sensor_events (
                event_id TEXT PRIMARY KEY,
                event_json TEXT NOT NULL,
                received_at TEXT NOT NULL,
                kafka_published_at TEXT
            )
        """)

        conn.execute(
            """
            INSERT INTO sensor_events
                (event_id, event_json, received_at)
            VALUES (?, ?, ?)
            """,
            ("event-1", "{}", received_at),
        )

    metrics = collect_metrics(db_path, now)

    assert metrics["total_events"] == 1
    assert metrics["pending_events"] == 1
    assert metrics["oldest_pending_age_seconds"] == pytest.approx(
        10.0, abs=1.0
    )
    assert metrics["latest_delivered_at"] is None
    assert metrics["sqlite_db_bytes"] > 0
