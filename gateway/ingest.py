"""
Subscribes to the greenhouse/telemetry MQTT topic, validates incoming events
against the JSON schema, and inserts valid, non-duplicate events into SQLite.

Initializes the database and table if they don't exist.
Provides a persistent buffer between MQTT ingestion and the Kafka producer.

Intended to run continuously on the Raspberry Pi.
"""

import json
import os
import sqlite3
import logging
from datetime import datetime, timezone
from pathlib import Path

import paho.mqtt.client as mqtt
from dotenv import load_dotenv
from jsonschema import ValidationError, validate

# Configuration
ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "gateway" / "data" / "sensor_events.db"

load_dotenv(ROOT / ".env")

MQTT_TOPIC = "greenhouse/telemetry"

SCHEMAS = {
        1: open(ROOT / "schemas" / "sensor_event.v1.schema.json"),
        2: open(ROOT / "schemas" / "sensor_event.v2.schema.json")
    }    


# Creates SQLite database and table.
def initialize_database():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("PRAGMA synchronous = FULL")
        conn.execute("PRAGMA busy_timeout = 30000")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sensor_events (
                event_id TEXT PRIMARY KEY,
                event_json TEXT NOT NULL,
                received_at TEXT NOT NULL,
                kafka_published_at TEXT
            )
        """)

# Subscribes to greenhouse/telemetry MQTT topic. Runs when connected to Mosquitto.
def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code.is_failure:
        print(f"Connection failed: {reason_code}")
        return

    client.subscribe(MQTT_TOPIC, qos=1)
    print(f"Subscribed to {MQTT_TOPIC}")

# Validates events.
def validate_event(event):
    version = event.get("schema_version")

    if version not in SCHEMAS:
        raise ValueError(
            f"Unsupported schema version: {version}"
        )

    validate(
        instance=event,
        schema=SCHEMAS[version],
    )

# Decodes JSON, validates against schema, inserts into SQLite table. Runs when Mosquitto delivers an event.
def on_message(client, userdata, message):
    """Persist a measurement before acknowledging MQTT delivery."""

    try:
        event = json.loads(message.payload.decode("utf-8"))
        validate_event(event)

    except (ValueError, ValidationError) as error:
        # Invalid messages cannot enter the outbox.
        # Log them explicitly; a later improvement will quarantine them.
        print(f"Invalid event: {error}")

        # Acknowledge intentionally rejected messages to avoid
        # repeatedly processing the same malformed payload.
        rc = client.ack(message.mid, message.qos)
        if rc != mqtt.MQTT_ERR_SUCCESS:
            raise RuntimeError(f"MQTT acknowledgment failed: {rc}")

        return

    received_at = datetime.now(timezone.utc).isoformat()

    try:
        # The inner context commits before we acknowledge the message.
        with sqlite3.connect(DB_PATH, timeout=30) as conn:
            result = conn.execute(
                """
                INSERT OR IGNORE INTO sensor_events
                    (event_id, event_json, received_at)
                VALUES (?, ?, ?)
                """,
                (
                    event["event_id"],
                    json.dumps(event),
                    received_at,
                ),
            )

            inserted = result.rowcount == 1

    except sqlite3.Error:
        # Do not acknowledge a message that failed to persist.
        # Allow the exception to terminate the process so systemd
        # can restart it and the broker can redeliver the message.
        logging.exception("SQLite persistence failed")
        raise

    # We only get here after the SQLite transaction has committed.
    rc = client.ack(message.mid, message.qos)

    if rc != mqtt.MQTT_ERR_SUCCESS:
        raise RuntimeError(f"MQTT acknowledgment failed: {rc}")

    if inserted:
        print(f"Saved: {event['measurement_type']} = {event['value']}")
    else:
        print(f"Duplicate ignored: {event['event_id']}")

# Main service
def main():

    # Create database and table if they don't already exist.
    initialize_database()

    # Connect to Mosquitto, subscribe to greenhouse/telemetry topic, insert events into SQLite table.
    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id="pi-sqlite-ingestor",
        protocol=mqtt.MQTTv311,
        clean_session=False,
        manual_ack=True,
    )

    client.username_pw_set(
        os.getenv("MQTT_USERNAME"),
        os.getenv("MQTT_PASSWORD")
    )

    client.on_connect = on_connect
    client.on_message = on_message

    client.connect("localhost", 1883, keepalive=60)

    print("Starting SQLite ingestion...")
    client.loop_forever()


if __name__ == "__main__":
    main()
