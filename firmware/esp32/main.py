
"""
ESP32 greenhouse telemetry publisher.

Sensors -> ESP32 -> MQTT -> Raspberry Pi

Publishes schema v2 events continuously.
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
SENSOR_RETRY_SECONDS = 30
NTP_RESYNC_SECONDS = 3600


def generate_event_id():
    """Generate a UUID version 4."""

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
    """Return an ISO 8601 UTC timestamp."""

    now = time.gmtime()

    if now[0] < 2025:
        raise RuntimeError("Clock is not synchronized")

    return "%04d-%02d-%02dT%02d:%02d:%02dZ" % now[:6]


def sync_clock():
    """Synchronize the device clock using NTP."""

    ntptime.settime()
    print("UTC synchronized:", utc_timestamp())


def create_event(measurement, timestamp):
    """Convert a measurement into a schema v2 event."""

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


def collect_events(sensor_devices):
    """Collect all available measurements."""

    measurements = sensors.read_all(sensor_devices)

    if not measurements:
        return []

    timestamp = utc_timestamp()

    return [
        create_event(measurement, timestamp)
        for measurement in measurements
    ]


def connect_mqtt():
    """Connect to the Raspberry Pi MQTT broker."""

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


def publish_pending(client, pending_events):
    """
    Publish pending events using MQTT QoS 1.

    Remove events only after successful publication.
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
    """Run the continuous greenhouse publisher."""

    print("Starting greenhouse ESP32...")

    sensor_devices = sensors.init_all()

    wlan = None
    client = None
    pending_events = []

    last_ntp_sync = None
    last_sensor_retry = time.ticks_ms()

    next_sample = time.ticks_ms()
    next_network_retry = time.ticks_ms()

    while True:
        try:
            now_ms = time.ticks_ms()

            # 1. Retry unavailable sensors independently.
            if time.ticks_diff(
                now_ms, last_sensor_retry
            ) >= SENSOR_RETRY_SECONDS * 1000:

                sensors.retry_failed(sensor_devices)
                last_sensor_retry = time.ticks_ms()

            # 2. Reconnect network services when needed.
            if wlan is None or not wlan.isconnected():
                if time.ticks_diff(
                    now_ms, next_network_retry
                ) < 0:
                    time.sleep_ms(100)
                    continue

                wlan = connect_wifi()
                client = None

            # 3. Synchronize UTC on startup and periodically.
            if (
                last_ntp_sync is None
                or time.ticks_diff(
                    time.ticks_ms(), last_ntp_sync
                ) >= NTP_RESYNC_SECONDS * 1000
            ):
                try:
                    sync_clock()
                    last_ntp_sync = time.ticks_ms()
                except Exception as exc:
                    print("NTP synchronization failed:", exc)

                    # Do not publish with an invalid clock.
                    if time.gmtime()[0] < 2025:
                        raise

                    # A previously synchronized clock can
                    # continue operating until the next retry.
                    last_ntp_sync = time.ticks_ms()

            # 4. Establish MQTT connection.
            if client is None:
                client = connect_mqtt()

            # 5. Retry pending events before new sampling.
            if pending_events:
                publish_pending(client, pending_events)

            # 6. Collect and publish new measurements.
            now_ms = time.ticks_ms()

            if time.ticks_diff(now_ms, next_sample) >= 0:
                pending_events = collect_events(sensor_devices)

                if pending_events:
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

            # Disconnect and recreate the MQTT client.
            if client is not None:
                try:
                    client.disconnect()
                except Exception:
                    pass

            client = None

            # Schedule a retry without terminating the loop.
            next_network_retry = time.ticks_add(
                time.ticks_ms(),
                RETRY_SECONDS * 1000,
            )

            # Mark Wi-Fi unavailable so reconnect is checked.
            wlan = None

            print("Network retry in", RETRY_SECONDS, "seconds")

            time.sleep_ms(100)

    if client is not None:
        try:
            client.disconnect()
        except Exception:
            pass


if __name__ == "__main__":
    main()
