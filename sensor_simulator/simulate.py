"""
Simulates sensor measurements by generating 3 synthetic measurements per second,
validating measurements against json schema in schemas/, and publishing to
MQTT broker on the Raspberry Pi.

Intended to run continuously (optionally) to simulate load greater than that of the physical sensors.
"""
import json
import os
import random
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv
import paho.mqtt.client as mqtt
from jsonschema import Draft202012Validator, FormatChecker

# Configuration
ROOT = Path(__file__).resolve().parent.parent

load_dotenv(ROOT / ".env")

# Raspberry Pi MQTT broker
MQTT_HOST = os.getenv("MQTT_HOST")
MQTT_PORT = int(os.getenv("MQTT_PORT"))
MQTT_USERNAME = os.getenv("MQTT_USERNAME")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD")
MQTT_TOPIC = os.getenv("MQTT_TOPIC")

# Load JSON Schema
SCHEMA_PATH = ROOT / "schemas" / "sensor_event.schema.json"

with open(SCHEMA_PATH) as f:
    schema = json.load(f)

validator = Draft202012Validator(
    schema,
    format_checker=FormatChecker()
)

# Simulated starting conditions
soil_moisture = 475.0
air_temperature = 23.0
relative_humidity = 65.0

# Creates an event given necessary values
def make_event(sensor_id, measurement_type, value, unit, timestamp):
    event = {
        "schema_version": 1,
        "event_id": str(uuid.uuid4()),
        "sensor_id": sensor_id,
        "gateway_id": "pi-001",
        "timestamp": timestamp,
        "measurement_type": measurement_type,
        "value": value,
        "unit": unit
    }

    validator.validate(event)
    return event

# Main service
def main():
    global soil_moisture, air_temperature, relative_humidity

    # Connect to Pi via MQTT
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)

    client.username_pw_set(
        MQTT_USERNAME,
        MQTT_PASSWORD
    )

    client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
    client.loop_start()

    print(f"Publishing MQTT events to {MQTT_HOST}...")
    
    try:
        # Loop to generate synthetic measurements
        while True:
            timestamp = datetime.now(timezone.utc).isoformat()

            soil_moisture = max(
                300, min(800, soil_moisture + random.uniform(-2, 2))
            )
            air_temperature = max(
                10, min(40, air_temperature + random.uniform(-0.15, 0.15))
            )
            relative_humidity = max(
                20, min(100, relative_humidity + random.uniform(-0.5, 0.5))
            )

            # Events for each measurement
            events = [
                make_event(
                    "soil-001", "soil_moisture",
                    round(soil_moisture), "raw_capacitance", timestamp
                ),
                make_event(
                    "bme280-001", "air_temperature",
                    round(air_temperature, 2), "celsius", timestamp
                ),
                make_event(
                    "bme280-001", "relative_humidity",
                    round(relative_humidity, 2), "percent", timestamp
                )
            ]

            for event in events:
                message = json.dumps(event)
                result = client.publish(MQTT_TOPIC, message, qos=1)
                result.wait_for_publish()
                print(message)

            time.sleep(1)

    except KeyboardInterrupt:
        print("\nStopping simulator...")

    finally:
        client.disconnect()
        client.loop_stop()


if __name__ == "__main__":
    main()