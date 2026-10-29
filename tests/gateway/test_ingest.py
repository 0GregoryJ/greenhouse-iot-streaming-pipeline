
import copy
import json
import sqlite3
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import paho.mqtt.client as mqtt
from jsonschema import ValidationError

from gateway import ingest


def make_message(event, mid=42):
    """Create a fake MQTT message."""

    return SimpleNamespace(
        topic="greenhouse/telemetry",
        payload=json.dumps(event).encode("utf-8"),
        qos=1,
        mid=mid,
    )


def test_valid_event_is_inserted(
    tmp_path,
    monkeypatch,
    valid_event,
):
    # 1. Create a temporary database path.
    db_path = tmp_path / "sensor_events.db"

    # 2. Point the ingestor to that database.
    monkeypatch.setattr(ingest, "DB_PATH", db_path)

    # 3. Create the database and table.
    ingest.initialize_database()

    # 4. Create a fake MQTT client and message.
    client = Mock()
    client.ack.return_value = mqtt.MQTT_ERR_SUCCESS

    msg = make_message(valid_event)

    # 5. Run the real MQTT callback.
    ingest.on_message(client, None, msg)

    # 6. Query the temporary SQLite database.
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT event_id, event_json, received_at,
                   kafka_published_at
            FROM sensor_events
            WHERE event_id = ?
            """,
            (valid_event["event_id"],),
        ).fetchone()

    # 7. Verify the event was saved.
    assert row is not None

    event_id, event_json, received_at, published_at = row

    assert event_id == valid_event["event_id"]
    assert json.loads(event_json) == valid_event
    assert received_at is not None
    assert published_at is None

    # 8. Verify MQTT acknowledgment.
    client.ack.assert_called_once_with(
        msg.mid,
        msg.qos,
    )


def test_accepts_valid_v2_event(valid_event):
    event = copy.deepcopy(valid_event)

    # No exception means validation succeeded.
    ingest.validate_event(event)


def test_rejects_missing_event_id(valid_event):
    event = copy.deepcopy(valid_event)
    del event["event_id"]

    with pytest.raises(ValidationError):
        ingest.validate_event(event)


def test_rejects_unsupported_version(valid_event):
    event = copy.deepcopy(valid_event)
    event["schema_version"] = 999

    with pytest.raises(ValueError):
        ingest.validate_event(event)
