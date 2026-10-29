# ADR 0001: MQTT with Mosquitto for device-to-gateway ingestion

**Status:** Accepted
**Recorded:** 2026-10-28

## Context

The ESP32 runs MicroPython with limited memory and no local disk. It needs a small, widely supported protocol that works over Wi-Fi to a gateway on the same LAN, tolerates reconnects, and lets the sender know when the receiver has the message. The gateway must be able to stop and restart without losing messages that arrive meanwhile.

MicroPython ships with `umqtt.simple`, and Mosquitto runs comfortably on a Raspberry Pi Zero 2 W.

## Decision

Devices publish JSON events to Mosquitto on the Pi, topic `greenhouse/telemetry`, with MQTT QoS 1. Mosquitto requires a username and password and listens on port 1883 ([`infrastructure/mosquitto/greenhouse.conf`](../../infrastructure/mosquitto/greenhouse.conf)).

The ingest service connects with a fixed client ID (`pi-sqlite-ingestor`), `clean_session=False`, a QoS 1 subscription, and `manual_ack=True`, so the broker queues messages while ingest is down and redelivers anything that was not acknowledged ([ADR 0002](0002-sqlite-outbox-on-the-gateway.md)).

## Consequences

- The firmware's `Published:` log line is printed only after the broker's PUBACK, which makes device-side debugging direct.
- A restart of ingest does not drop messages; Mosquitto holds them for the persistent session.
- QoS 1 is at-least-once, so the same message can arrive twice. Deduplication is handled by `event_id` ([ADR 0003](0003-at-least-once-delivery-with-event-id-deduplication.md)).
- Transport is plain TCP with password authentication. The broker is meant for the greenhouse LAN. TLS and per-device ACLs are on the [roadmap](../../README.md#roadmap).
- The simulator and the ESP32 publish through the same entry point; the simulator's IDs carry a `sim-` prefix so its events are distinguishable from real ones.

## Related

[Architecture](../architecture.md#event-flow), [`gateway/ingest.py`](../../gateway/ingest.py), [`firmware/esp32/main.py`](../../firmware/esp32/main.py)
