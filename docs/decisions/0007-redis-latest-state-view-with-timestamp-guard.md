# ADR 0007: Redis latest-state view with a timestamp-guarded update

**Status:** Accepted
**Recorded:** 2026-10-28

## Context

The dashboard needs the latest value per sensor and measurement with low latency, and should not query Kafka or SQLite. The view is derived data: Kafka holds the source of truth. Kafka can redeliver events, and after an outage the Pi sends a backlog, so events arrive out of order relative to event time.

## Decision

A live consumer reads the topic and maintains one Redis hash per `gateway_id`, `sensor_id`, and `measurement_type` under `greenhouse:latest:{...}`. An atomic Lua script updates the hash only if the stored `timestamp_ms` is not newer than the incoming one. The consumer commits its Kafka offset synchronously after the Redis call returns, with `auto.offset.reset=earliest` and no auto-commit. Redis runs under Docker Compose with AOF persistence on a volume and no host port. FastAPI reads Redis only, and Caddy is the public HTTPS entry point.

## Consequences

- Replays, duplicates, and backlog drains cannot move a reading backwards, because older timestamps are ignored.
- A Redis error stops the consumer without committing, so the message is reprocessed after the restart.
- Redis can be rebuilt from Kafka by starting the consumer with a new group. The recovery procedure is documented ([Operations](../operations.md#4-kafka-has-events-but-redis-is-empty)); automating and testing it end to end is on the [roadmap](../../README.md#roadmap).
- The API stays simple and fast, and it never touches Kafka.
- Keys have no TTL, so a retired sensor's key is removed manually.
- The guard compares event timestamps, so a reading with a timestamp ahead of real time holds the key until real time catches up.
- The view holds only the latest value. History belongs to the analytics path.

## Related

[Architecture](../architecture.md#event-flow), [`consumers/live/consumer.py`](../../consumers/live/consumer.py), [`api/main.py`](../../api/main.py), [`tests/consumers/test_live_consumer.py`](../../tests/consumers/test_live_consumer.py), [`tests/api/test_api.py`](../../tests/api/test_api.py)
