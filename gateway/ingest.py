#---
# Subscribes to the greenhouse/telemetry MQTT topic,
# validates incoming events against the JSON schema,
# and inserts valid, non-duplicate events into SQLite.
#
# Initializes the database and table if they don't exist.
# Provides a persistent buffer between MQTT ingestion
# and the downstream Kafka producer.
#---

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import paho.mqtt.client as mqtt
from dotenv import load_dotenv
from jsonschema import Draft202012Validator, FormatChecker, ValidationError


ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "gateway" / "data" / "sensor_events.db"

load_dotenv(ROOT / ".env")

MQTT_TOPIC = "greenhouse/telemetry"


with open(ROOT / "schemas" / "sensor_event.schema.json") as f:
    schema = json.load(f)

validator = Draft202012Validator(
    schema,
    format_checker=FormatChecker()
)

# Creates SQLite database and table.
def initialize_database():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(DB_PATH) as conn:
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

# Decodes JSON, validates against schema, inserts into SQLite table. Runs when Mosquitto delivers an event.
def on_message(client, userdata, message):
    try:
        event = json.loads(message.payload.decode("utf-8"))
        validator.validate(event)

        received_at = datetime.now(timezone.utc).isoformat()

        with sqlite3.connect(DB_PATH) as conn:
            result = conn.execute(
                """
                INSERT OR IGNORE INTO sensor_events
                (event_id, event_json, received_at)
                VALUES (?, ?, ?)
                """,
                (
                    event["event_id"],
                    json.dumps(event),
                    received_at
                )
            )

        if result.rowcount == 1:
            print(f"Saved: {event['measurement_type']} = {event['value']}")
        else:
            print(f"Duplicate ignored: {event['event_id']}")

    except (ValueError, ValidationError) as error:
        print(f"Invalid event: {error}")

    except sqlite3.Error as error:
        print(f"Database error: {error}")


def main():

    # Create database and table if they don't already exist.
    initialize_database()

    # Connect to Mosquitto, subscribe to greenhouse/telemetry topic, insert events into SQLite table.
    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id="pi-sqlite-ingestor"
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
