# ADR 0002: SQLite outbox on the Raspberry Pi gateway

**Status:** Accepted
**Recorded:** 2026-10-28

## Context

Kafka runs on AWS and the Pi reaches it over the internet through Tailscale. Home networks, the WAN, and the broker can all be unavailable for minutes or hours. The edge must keep accepting sensor events during those outages and forward them when the path recovers. The gateway needs a durable buffer that survives process crashes and power loss, with little operational overhead on a small device.

## Decision

Ingest writes each valid event to a local SQLite table (`sensor_events`) before acknowledging the MQTT message. The table is an outbox:

- `event_id` is the primary key, and inserts use `INSERT OR IGNORE`.
- The connection uses `PRAGMA synchronous = FULL`.
- `kafka_published_at` is `NULL` until the Kafka producer receives the broker's delivery acknowledgment.
- A separate producer service reads pending rows, publishes them, and sets `kafka_published_at` only for acknowledged rows.
- A cleanup timer deletes acknowledged rows older than 24 hours. Pending rows are never deleted by age.

Ingest and producer are separate systemd services, so a Kafka outage never blocks ingestion.

## Consequences

- Events are durable from the moment SQLite commits. Anything before that point (the ESP32's RAM) is not.
- During a Kafka or WAN outage, `pending` grows and drains oldest-first after recovery. Disk usage is the limit, and the health check warns at 80 % and 90 %.
- A crash between "Kafka acknowledged" and "row marked" resends the row, so Kafka can hold duplicates ([ADR 0003](0003-at-least-once-delivery-with-event-id-deduplication.md)).
- The database is a buffer, not a history store. Long-term history is planned through a second Kafka consumer group ([roadmap](../../README.md#roadmap)).
- Schema changes to the table are applied by hand (`gateway/migrations/`).
- SQLite allows one writer at a time. The services use `busy_timeout` and the load (about 48 events per minute) is far below its limits.

## Related

[Architecture](../architecture.md#what-is-stored-where), [`gateway/ingest.py`](../../gateway/ingest.py), [`gateway/kafka_producer.py`](../../gateway/kafka_producer.py), [`gateway/cleanup.py`](../../gateway/cleanup.py)
