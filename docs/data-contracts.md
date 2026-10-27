# Data contracts

The sensor event schema, where it is enforced, and how to change it without breaking ingestion or downstream consumers.

Related documents: [Architecture](architecture.md) · [Adding a sensor](adding-a-sensor.md) · [Deployment](deployment.md) · [Operations](operations.md)

## Schema versions

| Version | Schema | Example | Emitted by | Accepted by gateway |
| --- | --- | --- | --- | --- |
| 1 | [`sensor_event.v1.schema.json`](../schemas/sensor_event.v1.schema.json) | [`sensor_event.v1.example.json`](../schemas/sensor_event.v1.example.json) | Simulator | Yes |
| 2 | [`sensor_event.v2.schema.json`](../schemas/sensor_event.v2.schema.json) | [`sensor_event.v2.example.json`](../schemas/sensor_event.v2.example.json) | ESP32 firmware (`SCHEMA_VERSION = 2` in `main.py`) | Yes |

Both are JSON Schema draft 2020-12. The gateway selects the schema from the event's `schema_version`; any other value is rejected as unsupported. v2 is a superset of v1: it adds `atmospheric_pressure` and `hpa`, and pins `atmospheric_pressure` to `hpa`. Validation is otherwise identical.

## Fields

All eight fields are required in both versions. `additionalProperties` is `false`, so unknown fields are rejected.

| Field | Type | Constraint | Notes |
| --- | --- | --- | --- |
| `schema_version` | integer | `const`: 1 or 2 | Selects the validation schema |
| `event_id` | string | `format: uuid` | Deduplication key: SQLite primary key and Kafka message key. The firmware generates UUIDv4 |
| `sensor_id` | string | `minLength: 1` | Identifies the physical sensor, e.g. `bme280-001` |
| `gateway_id` | string | `minLength: 1` | Set by the ESP32 from `config.GATEWAY_ID`, e.g. `pi-001` |
| `timestamp` | string | `format: date-time` | UTC time of the sample. The firmware emits `YYYY-MM-DDTHH:MM:SSZ` |
| `measurement_type` | string | enum (below) | |
| `value` | number | `type: number` | Integers and floats are accepted. Booleans and strings are rejected |
| `unit` | string | enum (below) | |

### Measurement types and units

| `measurement_type` | v1 | v2 | Unit as emitted today | Source |
| --- | --- | --- | --- | --- |
| `air_temperature` | yes | yes | `celsius` | BME280 |
| `relative_humidity` | yes | yes | `percent` | BME280 |
| `atmospheric_pressure` | no | yes | `hpa` (enforced) | BME280 |
| `soil_moisture` | yes | yes | `raw_capacitance` (uncalibrated) | STEMMA soil sensor |
| `soil_temperature` | yes | yes | not emitted by the current firmware | Schema only |

Permitted `unit` values: `raw_capacitance`, `celsius`, `percent` (v1 and v2), plus `hpa` (v2 only).

The schema does **not** pair units with measurement types, with one exception: in v2, `atmospheric_pressure` must use `hpa` (an `allOf`/`if`/`then` rule). Other combinations, such as `air_temperature` with `hpa`, validate. Correct pairing is a firmware responsibility.

## Examples

Schema v1, from [`sensor_event.v1.example.json`](../schemas/sensor_event.v1.example.json):

```json
{
  "schema_version": 1,
  "event_id": "550e8400-e29b-41d4-a716-446655440000",
  "sensor_id": "soil-001",
  "gateway_id": "pi-001",
  "timestamp": "2026-10-20T19:30:00Z",
  "measurement_type": "soil_moisture",
  "value": 475,
  "unit": "raw_capacitance"
}
```

Schema v2, from [`sensor_event.v2.example.json`](../schemas/sensor_event.v2.example.json):

```json
{
  "schema_version": 2,
  "event_id": "550e8400-e29b-41d4-a716-446655440003",
  "sensor_id": "bme280-001",
  "gateway_id": "pi-001",
  "timestamp": "2026-10-27T05:30:00Z",
  "measurement_type": "atmospheric_pressure",
  "value": 1013.2,
  "unit": "hpa"
}
```

## One measurement per event

Each event carries exactly one `(sensor_id, measurement_type, value, unit)`. A BME280 cycle therefore produces three events that share a `timestamp`; the soil sensor adds a fourth.

Why it works for this pipeline:

- A new measurement type is a new enum value, not a new field or a wider event shape.
- `event_id` deduplicates at measurement granularity, so partial retries are safe.
- The Redis key `greenhouse:latest:{gateway_id}:{sensor_id}:{measurement_type}` maps one-to-one to events, so the consumer needs no per-sensor logic.
- The producer, consumer, and API are agnostic to which sensors exist.

Trade-offs: more messages (48 per minute at a 5 s interval with the current sensors), and no atomic multi-measurement snapshot. Readings from one cycle share a timestamp but are separate events and can arrive or fail independently.

## Where validation happens

| Stage | What is checked | Notes |
| --- | --- | --- |
| ESP32 (`main.py`) | Nothing against the schema | Builds events from constants and `float(value)`. Clock must be at least year 2025 |
| Simulator | Schema v1 with `FormatChecker` | Stops on any invalid event it generates |
| Mosquitto | Authentication only | No payload validation, no topic ACLs in the repo config |
| **Gateway ingest** | Full JSON Schema by `schema_version`, **without** a format checker | The authoritative gate. `uuid` and `date-time` formats are **not** enforced here: a non-UUID `event_id` or a naive timestamp passes |
| Kafka producer | Nothing | Forwards the stored JSON unchanged |
| Kafka | Nothing | No schema registry |
| Live consumer | Presence of `event_id`, `sensor_id`, `gateway_id`, `measurement_type`, `timestamp`, `value`, `unit`; timestamp parses with `datetime.fromisoformat` and has a timezone; `value` is `int` or `float` | Stricter than the gateway on timestamps; looser everywhere else. It ignores `schema_version`, enums, and extra fields |
| API | `float(record["value"])` | Failure returns HTTP 503 |
| Dashboard | Unit-based formatting; unknown types get a generic label | No validation |

## How invalid events are handled

| Where | Condition | Behavior | Event kept? |
| --- | --- | --- | --- |
| Ingest | Malformed JSON, non-UTF-8, unsupported `schema_version`, or schema violation | Logs `Invalid event: <error>` and **acknowledges** the MQTT message so it is not redelivered | No. Logged and dropped |
| Consumer | Missing field, unparsable or timezone-less timestamp, non-numeric value | Logs `Skipping malformed event at partition=… offset=…` and commits the offset | No. Still in Kafka until retention expires |

Rejected-event storage (a table or dead-letter queue with bounded retention) is **Planned**. Until then, the only record of a rejected event is a journal line, and that line carries the validation error, not the payload.

Gaps observed from reading `ingest.py` (not exercised against a running broker):

- A payload that is valid JSON but not an object (for example `[]`), or a `schema_version` that is not a hashable scalar, raises outside the `except (ValueError, ValidationError)` clause. The callback raises, the process exits, and the message is unacknowledged. With a persistent session it can be redelivered after the restart, which risks a restart loop. See [Operations](operations.md#poison-message-restart-loop).
- Because formats are not enforced, an event can pass the gateway and then be skipped by the consumer (for example a timestamp without a timezone).

## Compatibility rules

Terms used here:

- **Additive**: existing valid events stay valid under the changed schema, and components that have not been updated keep working on existing traffic.
- **Breaking**: some existing valid event becomes invalid, or the meaning of existing data changes.

Because the gateway schema is closed (`additionalProperties: false`, fixed enums), **any new field or enum value is rejected by a gateway that has not been updated**. "Additive" therefore does not mean "deploy in any order". The gateway must be updated before any producer emits the new shape.

| Change | Class | Needs a new `schema_version`? | Notes |
| --- | --- | --- | --- |
| New `measurement_type` or `unit` value | Additive | Recommended | Precedent: v2 added `atmospheric_pressure` and `hpa` as a new version, leaving v1 untouched |
| New optional field | Additive | Yes | Must be added to `properties` but not `required`. Downstream ignores it until consumer/API are updated |
| New required field | Breaking for producers | Yes | Events of the old version must still be accepted until every producer is upgraded |
| Remove or rename a field | Breaking | Yes | Consumer reads seven fields by name |
| Change a field's type or format | Breaking | Yes | |
| Narrow an enum or tighten a constraint | Breaking | Yes | |
| Change units or semantics of an existing type (for example calibrating `soil_moisture`) | Breaking (semantic) | Prefer a new `unit` value, or a new `measurement_type` | Redis holds one value per key; mixed meanings under one key are indistinguishable. `raw_capacitance` must stay raw |
| Change timestamp format | Breaking | Yes | Consumer and dashboard parse ISO 8601 |
| Change what `event_id` means | Breaking | Yes | Deduplication and Kafka key depend on it |
| Change `sensor_id`/`gateway_id`/`measurement_type` values for existing devices | Breaking (data) | n/a | Changes Redis keys; the old keys remain as stale cards |

Rules for a new version:

1. Add `schemas/sensor_event.vN.schema.json` and `schemas/sensor_event.vN.example.json`. Keep earlier versions unchanged while any producer or stored event uses them.
2. Register it in the `SCHEMAS` dict in [`gateway/ingest.py`](../gateway/ingest.py). Schemas are loaded at process start, so ingest must be restarted.
3. Bump `SCHEMA_VERSION` in the firmware's `main.py` only after the gateway accepts the new version.
4. Do not retire a version while old events may still be in an MQTT queue, the SQLite outbox, or Kafka (168 h by default). The producer and consumer do not look at `schema_version`, so retained events of old versions still flow.
5. Future aggregating consumers (Flink, Snowflake, dbt; **Planned**) must handle every version present in retained data and deduplicate on `event_id`.

## What to check after a contract change

| Component | Check | Needed when |
| --- | --- | --- |
| `schemas/` | Schema, example, `$schema` valid | Always |
| [`gateway/ingest.py`](../gateway/ingest.py) | Version registered in `SCHEMAS`; service restarted | New version |
| Firmware [`main.py`](../firmware/esp32/main.py), [`sensors.py`](../firmware/esp32/sensors.py) | `SCHEMA_VERSION`, event fields, measurement types, units | Producer-side change |
| Simulator | Pinned to v1 (`schema_version: 1`, `schemas/sensor_event.v1.schema.json`) | If the simulator should emit the new shape |
| SQLite outbox | Stores the event as a JSON string. No column change | Never for content changes. Only if outbox columns change |
| [`gateway/kafka_producer.py`](../gateway/kafka_producer.py) | Forwards JSON unchanged | Never for content changes |
| Kafka topic | No registry; key is `event_id` | Only if key or topic design changes |
| [`consumers/live/consumer.py`](../consumers/live/consumer.py) | Reads the seven fields, ignores the rest | Only if the live view needs a new field, or the Redis key structure changes |
| Redis | New keys appear automatically | Only if key structure or stored fields change. Old keys need manual cleanup |
| [`api/main.py`](../api/main.py) | Builds the response from fixed hash fields; `value` must be numeric | Only if the response shape changes |
| [`dashboard/src/App.jsx`](../dashboard/src/App.jsx) | Label and order in `METRICS`; `formatValue` for the unit | Optional for new types (generic fallback exists); needed for a unit that requires special formatting |
| `tests/` | Add coverage for any code you changed | Code changes |
| `docs/` | This file, [Adding a sensor](adding-a-sensor.md), the root README | Always |

## Testing a schema change before deployment

There is no staging environment and no schema-specific test in CI today (CI runs `tests/gateway/` only).

**1. Validate schemas and examples locally** (same validation settings as the gateway; run from the repository root with the gateway dependencies installed):

```bash
.venv/bin/python - <<'EOF'
import json
from pathlib import Path
from jsonschema import Draft202012Validator

for v in (1, 2):  # add your new version
    schema = json.loads(Path(f"schemas/sensor_event.v{v}.schema.json").read_text())
    example = json.loads(Path(f"schemas/sensor_event.v{v}.example.json").read_text())
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(example)
    print(f"v{v}: schema valid, example accepted")
EOF
```

**2. Check negative cases** against both the new and old versions: an old-version event still passes its own version, a new-only value is rejected by the old version, and an extra field is rejected. A durable schema contract test under `tests/` is **Planned**.

**3. Run existing tests:**

```bash
.venv/bin/python -m pytest tests/gateway/ -v
```

**4. Replicate firmware output.** Run a representative event from `create_event()` in `main.py` through the validator. The firmware is MicroPython, so test the dictionary shape on the host or review it by hand.

**5. After deploying the gateway**, publish one clearly labelled test event on the Pi and confirm it reaches SQLite. This event also flows to Kafka, Redis, and the dashboard, so use a dedicated `sensor_id` and delete its Redis key afterwards. Commands are in [Adding a sensor](adding-a-sensor.md#test-the-gateway-with-a-synthetic-event).

For rollout order across components, see [Deployment](deployment.md#coordinated-changes-and-schema-migrations).
