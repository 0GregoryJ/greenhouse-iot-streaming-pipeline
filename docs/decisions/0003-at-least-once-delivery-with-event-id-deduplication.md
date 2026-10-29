# ADR 0003: At-least-once delivery with deduplication by `event_id`

**Status:** Accepted
**Recorded:** 2026-10-28

## Context

Every hop in the pipeline can fail between "the receiver has it" and "the sender knows". Losing a sensor reading is worse than seeing it twice, and the end of the pipeline (a latest-value view) is naturally tolerant of repeats. Exactly-once delivery across MQTT, SQLite, Kafka, and Redis would need coordination across all four.

## Decision

Each hop acknowledges only after the next durable step, and duplicates are removed by identity instead of being prevented:

- The ESP32 assigns every event a random UUIDv4 `event_id` and retries until the broker acknowledges (QoS 1).
- Ingest commits to SQLite before it acknowledges MQTT. The `event_id` primary key with `INSERT OR IGNORE` drops redeliveries.
- The producer uses `acks=all` and an idempotent producer, marks a row only after its delivery callback succeeds, and uses `event_id` as the Kafka message key.
- The live consumer commits its Kafka offset synchronously after the Redis write.
- The Redis update is idempotent: a Lua script skips an update when the stored `timestamp_ms` is strictly newer.

## Consequences

- No acknowledged event is lost between the Pi's SQLite commit and Redis, under the failures the design covers.
- Duplicates can occur at the ESP32, in Kafka (a crash after delivery but before the row is marked), and at the consumer after a crash. SQLite and Redis absorb them.
- Kafka does not deduplicate. Consumers that aggregate (the planned Flink, Snowflake, and dbt work) deduplicate on `event_id`.
- Redis converges on the event with the greatest timestamp, so replays and out-of-order delivery cannot move a reading backwards.
- Because ordering in Kafka is arrival order at the Pi, event-time logic belongs in consumers.
- The Redis guard trusts event timestamps. The firmware publishes only after the clock is synchronized.

## Related

[Architecture: delivery guarantees](../architecture.md#delivery-guarantees), [`consumers/live/consumer.py`](../../consumers/live/consumer.py), [`tests/consumers/test_live_consumer.py`](../../tests/consumers/test_live_consumer.py)
