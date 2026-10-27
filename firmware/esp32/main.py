
"""
ESP32 greenhouse telemetry publisher.

Hardware:
    Adafruit ESP32 Feather V2

Pipeline:
    Sensors -> ESP32 -> MQTT -> Raspberry Pi

Event contract:
    One JSON event per measurement, schema v2.
"""

import json
import os
import time
import ntptime

from umqtt.simple import MQTTClient

import config
import sensors
from wifi import connect_wifi


SCHEMA_VERSION = 2
RETRY_SECONDS = 5
NTP_RESYNC_SECONDS = 3600


def generate_event_id():
    """Generate a random UUID version 4."""
    data = bytearray(os.urandom(16))
    data[6] = (data[6] & 0x0F) | 0x40
    data[8] = (data[8] & 0x3F) | 0x80

    value = "".join("%02x" % byte for byte in data)

    return "{}-{}-{}-{}-{}".format(
        value[:8],
        value[8:12],
        value[12:16],
        value[16:20],
        value[20:],
    )


def utc_timestamp():
    """Return the current time as an ISO 8601 UTC string."""
    now = time.gmtime()

    if now[0] < 2025:
        raise RuntimeError("Clock is not synchronized")

    return "%04d-%02d-%02dT%02d:%02d:%02dZ" % now[:6]


def sync_clock():
    """Synchronize ESP32 clock with an NTP server."""
    ntptime.settime()
    print("UTC synchronized:", utc_timestamp())


def create_event(measurement, timestamp):
    """
    Convert a sensor measurement into a schema v2 event.

    Expected measurement:
        {
            "sensor_id": "bme280-001",
            "measurement_type": "air_temperature",
            "value": 23.4,
            "unit": "celsius"
        }
    """
    return {
        "schema_version": SCHEMA_VERSION,
        "event_id": generate_event_id(),
        "sensor_id": measurement["sensor_id"],
        "gateway_id": config.GATEWAY_ID,
        "timestamp": timestamp,
        "measurement_type": measurement["measurement_type"],
        "value": float(measurement["value"]),
        "unit": measurement["unit"],
    }


def connect_mqtt():
    """Create and connect an MQTT client."""
    client = MQTTClient(
        client_id=config.MQTT_CLIENT_ID,
        server=config.MQTT_HOST,
        port=config.MQTT_PORT,
        user=config.MQTT_USERNAME,
        password=config.MQTT_PASSWORD,
        keepalive=30,
    )

    client.connect()
    print("Connected to MQTT:", config.MQTT_HOST)
    return client


def collect_events(sensor_devices):
    """Collect measurements from all sensors."""
    measurements = sensors.read_all(sensor_devices)
    timestamp = utc_timestamp()

    return [
        create_event(measurement, timestamp)
        for measurement in measurements
    ]


def publish_pending(client, pending_events):
    """
    Publish queued events using MQTT QoS 1.

    Remove an event only after publish() succeeds.
    """
    while pending_events:
        event = pending_events[0]

        client.publish(
            config.MQTT_TOPIC,
            json.dumps(event),
            qos=1,
        )

        print(
            "Published:",
            event["sensor_id"],
            event["measurement_type"],
            event["value"],
            event["unit"],
        )

        pending_events.pop(0)


def main():
    """Run the continuous telemetry publisher."""
    print("Starting greenhouse ESP32...")

    # Initialize physical sensors once.
    sensor_devices = sensors.init_all()

    client = None
    pending_events = []
    last_ntp_sync = None

    # Timestamp of the next sampling cycle.
    next_sample = time.ticks_ms()

    while True:
        try:
            # 1. Connect or reconnect Wi-Fi.
            wlan = connect_wifi()

            if not wlan.isconnected():
                raise RuntimeError("Wi-Fi unavailable")

            # 2. Synchronize UTC on startup and periodically.
            now_ms = time.ticks_ms()

            if (
                last_ntp_sync is None
                or time.ticks_diff(
                    now_ms, last_ntp_sync
                ) >= NTP_RESYNC_SECONDS * 1000
            ):
                sync_clock()
                last_ntp_sync = time.ticks_ms()

            # 3. Establish MQTT connection when needed.
            if client is None:
                client = connect_mqtt()

            # 4. Retry unsent events before sampling again.
            if pending_events:
                publish_pending(client, pending_events)

            # 5. Sample at the configured interval.
            now_ms = time.ticks_ms()

            if time.ticks_diff(now_ms, next_sample) >= 0:
                pending_events = collect_events(sensor_devices)
                publish_pending(client, pending_events)

                next_sample = time.ticks_add(
                    time.ticks_ms(),
                    config.SAMPLE_INTERVAL_SECONDS * 1000,
                )

            time.sleep_ms(100)

        except KeyboardInterrupt:
            print("Telemetry publisher stopped")
            break

        except Exception as exc:
            print("Telemetry error:", exc)
            print("Retrying in", RETRY_SECONDS, "seconds")

            if client is not None:
                try:
                    client.disconnect()
                except Exception:
                    pass

            client = None
            time.sleep(RETRY_SECONDS * 1)

    if client is not None:
        try:
            client.disconnect()
        except Exception:
            pass


if __name__ == "__main__":
    main()
