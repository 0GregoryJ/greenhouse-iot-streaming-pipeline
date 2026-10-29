# ADR 0005: Versioned, closed JSON Schemas validated at the gateway

**Status:** Accepted
**Recorded:** 2026-10-28

## Context

Events come from firmware that is updated by hand over USB and from a simulator, so different producers and versions coexist. Downstream stages (Kafka, Redis, the API, and future analytics) are only as reliable as the data admitted at the edge. Kafka has no schema registry in this deployment, and the Pi is the only place where every event passes through one process before being stored.

## Decision

- The contract is JSON Schema (draft 2020-12), one file per version in [`schemas/`](../../schemas/), with an example per version. Schemas are closed: `additionalProperties` is `false`, and `measurement_type` and `unit` are enums.
- Every event carries `schema_version`. Ingest picks the schema for that version from a dictionary in `ingest.py` and rejects unsupported versions.
- Ingest is the validation gate. Invalid events are logged, acknowledged, and dropped. The producer and Kafka forward stored JSON unchanged.
- Version 2 is a superset of version 1 (it adds `atmospheric_pressure` and `hpa`). Old versions stay registered while they may still be in flight.
- Rollout order is gateway first, then firmware.

## Consequences

- Bad data stops at the first durable stage, and a single place defines what is valid.
- v1 simulator events and v2 firmware events coexist during a transition.
- A closed schema rejects anything unknown, so any new field or enum value needs a gateway deployment before a device emits it ([Data contracts: compatibility rules](../data-contracts.md#compatibility-rules)).
- Adding a version is a code change (the `SCHEMAS` dictionary) and an ingest restart.
- `format` keywords (`uuid`, `date-time`) are not checked at the gateway. The consumer checks timestamps itself, so format enforcement at the gateway is on the [roadmap](../../README.md#roadmap).
- The downstream components ignore `schema_version`, which keeps them stable across versions but means retained events of older versions flow through unchanged.
- Rejected payloads are not stored yet; storing them is on the roadmap.

## Related

[Data contracts](../data-contracts.md), [`gateway/ingest.py`](../../gateway/ingest.py), [`tests/schemas/`](../../tests/schemas/), [`tests/gateway/test_ingest.py`](../../tests/gateway/test_ingest.py)
