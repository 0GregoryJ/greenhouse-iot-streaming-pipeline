# ADR 0004: One measurement per event

**Status:** Accepted
**Recorded:** 2026-10-28

## Context

A BME280 produces temperature, humidity, and pressure in one read, and the soil sensor produces moisture. Events could be shaped as one record per sensor reading with several value fields, or one record per measurement. The shape is the contract between the firmware, the gateway, Kafka, and every future consumer, so it is expensive to change.

## Decision

Each event carries exactly one `(sensor_id, measurement_type, value, unit)`. A BME280 cycle yields three events with a shared `timestamp`; the soil sensor adds a fourth. Every event has its own `event_id`.

## Consequences

- Adding a measurement type is a new enum value, not a wider event. Most new sensors need firmware changes only ([Adding a sensor](../adding-a-sensor.md)).
- Deduplication works at measurement granularity, so partial retries are safe.
- The Redis key `greenhouse:latest:{gateway_id}:{sensor_id}:{measurement_type}` maps one-to-one to events. The consumer, API, and dashboard need no per-sensor logic.
- A failed sensor drops out of a cycle without affecting the others.
- Message volume is higher: 48 events per minute at a 5 s interval with the current four measurements.
- Readings from one cycle share a timestamp but are separate events, so they can arrive at different times and there is no atomic multi-measurement snapshot.

## Related

[Data contracts](../data-contracts.md#one-measurement-per-event), [`schemas/`](../../schemas/)
