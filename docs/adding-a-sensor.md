# Adding a sensor

A step-by-step guide to adding a physical sensor to the ESP32 and carrying it through the pipeline. It uses the two existing integrations, the BME280 and the STEMMA soil sensor, as concrete examples.

Related documents: [Data contracts](data-contracts.md) · [Architecture](architecture.md) · [Deployment](deployment.md) · [Operations](operations.md) · [ESP32 firmware README](../firmware/esp32/README.md)

Most of the pipeline is sensor-agnostic. A sensor that emits a measurement type and unit the schema already allows needs **firmware changes only**. Read [What needs to change](#what-needs-to-change) before touching anything beyond `firmware/esp32/`.

## What needs to change

| Component | Change needed? | When |
| --- | --- | --- |
| Hardware, wiring | Yes | Always |
| Driver file in `firmware/esp32/` | Usually | If the sensor needs more than a few raw register reads |
| [`firmware/esp32/sensors.py`](../firmware/esp32/sensors.py) | **Yes** | Always: initialize the device and return its measurements |
| `config.py` and [`config.example.py`](../firmware/esp32/config.example.py) | **Yes** | Always: add the new `sensor_id` (and any pins/addresses you choose to configure) |
| [`firmware/esp32/main.py`](../firmware/esp32/main.py) | No | Unless the event shape changes. It calls `sensors.init_all()`, `sensors.retry_failed()`, and `sensors.read_all()` and sends whatever comes back |
| `schemas/` | Only if `measurement_type` or `unit` is not in the current schema | See [Does the schema support it?](#does-the-schema-support-it) |
| [`gateway/ingest.py`](../gateway/ingest.py) | Only for a **new schema version** | The `SCHEMAS` dict is hard-coded. Restart ingest after changing it |
| SQLite outbox, Kafka producer, Kafka topic | No | Events are stored and forwarded as opaque JSON |
| [Live consumer](../consumers/live/consumer.py) | No | It does not check measurement type or unit. It keys Redis by `gateway_id`/`sensor_id`/`measurement_type` |
| Redis | No | New keys appear on first event. Keys never expire, so cleanup is manual |
| [FastAPI](../api/main.py) | No | It returns every `greenhouse:latest:*` hash. `value` must be numeric |
| [Dashboard](../dashboard/src/App.jsx) | Optional | New types get a generic label and unformatted value. Edit for a proper label, order, or number format |
| Tests | When you change code that has tests or add logic | See [Tests](#tests) |
| Docs | Yes | See [Documentation updates](#documentation-updates) |

## 1. Choose and connect the hardware

| Interface | Used today? | Notes |
| --- | --- | --- |
| I²C over STEMMA QT | **Yes**, both sensors | Shared bus, daisy-chained cables, no soldering |
| I²C (other connectors) | No | Same bus and code. Wire to the Feather's SDA/SCL pins |
| Analog (ADC) | No | Use an ADC1 pin (see the checklist below) |
| Digital GPIO, 1-Wire, UART, SPI | No | Not used in this repo. Follow the same init, retry, and read pattern |

Bus configuration, from the constants at the top of `sensors.py`:

| Item | Value |
| --- | --- |
| STEMMA QT power enable | `STEMMA_POWER_PIN` = GPIO2, driven high, then a 500 ms wait |
| I²C | `SoftI2C`, `I2C_SDA_PIN` = GPIO22, `I2C_SCL_PIN` = GPIO20, `I2C_FREQUENCY` = 100 kHz |
| BME280 address | `BME280_ADDRESS` = `0x77` (the driver's default is `0x76`; the Adafruit board uses `0x77`) |
| Soil sensor address | `SOIL_ADDRESS` = `0x36` |

Checklist before wiring:

- **Voltage and current.** The STEMMA QT connector supplies 3.3 V through the GPIO2-enabled rail. Confirm the sensor's logic level and current draw.
- **Address conflicts.** Every device on the bus needs a unique address. Many boards expose address jumpers or pads; check the datasheet. Two identical sensors on one bus need different addresses.
- **Analog sensors.** On the ESP32, ADC2 pins cannot be used while Wi-Fi is active. Pick an ADC1 pin and check the Feather V2 pinout, since this firmware always uses Wi-Fi.
- **Cable length and pull-ups.** Long runs on a 100 kHz bus are usually fine, but add devices one at a time.

Connect the sensor with the ESP32 unplugged from USB, then power up.

## 2. Prove the sensor on the bench

Interrupt the running program (`Ctrl+C` in the REPL), then confirm the device is visible. Replace the port with yours (macOS: `ls /dev/cu.usbserial*`):

```bash
source .venv/bin/activate
export ESP32_PORT=/dev/cu.usbserial-XXXXXXXX
mpremote connect "$ESP32_PORT" repl
```

At the `>>>` prompt:

```python
from machine import Pin, SoftI2C
import time

Pin(2, Pin.OUT, value=1)     # STEMMA QT power
time.sleep_ms(500)

i2c = SoftI2C(sda=Pin(22), scl=Pin(20), freq=100000)
print([hex(a) for a in i2c.scan()])   # currently ['0x36', '0x77'] in some order
```

Add your sensor, rescan, and confirm the new address appears. Then read it once by hand before writing any project code. Setup details for the existing sensors are in the [firmware README](../firmware/esp32/README.md#3-connect-the-sensors).

## 3. Write or add a driver

Two patterns exist in the repo:

| Pattern | Example | Use when |
| --- | --- | --- |
| Driver module | [`bme280.py`](../firmware/esp32/bme280.py), a class taking `i2c=` and `address=` and exposing `.values` | A community MicroPython driver exists, or the sensor needs calibration math |
| Direct register read | `read_soil()` in `sensors.py` | One or two register reads, as with the STEMMA soil sensor's seesaw protocol |

```python
# Soil sensor: raw capacitance via seesaw (sensors.py)
i2c.writeto(SOIL_ADDRESS, bytes([0x0F, 0x10]))
time.sleep_ms(20)
raw = i2c.readfrom(SOIL_ADDRESS, 2)
return (raw[0] << 8) | raw[1]
```

If you add a driver file, remember that nothing copies it to the device automatically. Add a `mpremote fs cp` line for it when deploying ([Deploy the firmware](#7-deploy-and-verify)). Check the driver's licence before committing it; `bme280.py` keeps its original notice.

## 4. Edit `sensors.py` and configuration

`main.py` calls three functions from `sensors.py`. Everything else in that file is helper code.

| Function | Called by `main.py` | Contract |
| --- | --- | --- |
| `init_all()` | Once at boot | Power the bus and create the I²C object, build the `devices` dict (`"i2c"` plus one entry per sensor, initially `None`), call `retry_failed()`, and return the dict |
| `retry_failed(devices)` | At boot and every `SENSOR_RETRY_SECONDS` (30 s, set in `main.py`) | For each sensor whose entry is `None`, try to initialize it. Log success or failure; never raise |
| `read_all(devices)` | Every sample cycle | Read each available sensor inside its own `try`/`except`, append its measurements to a flat list, and set the entry to `None` if the read fails |

Per-sensor helpers follow a fixed shape: `init_<sensor>(i2c)` verifies the device and returns a handle (raising `RuntimeError` if it is not detected), and `read_<sensor>(handle)` returns plain numbers.

**Measurement contract.** `read_all()` returns dicts with exactly these keys. `main.create_event()` adds `schema_version`, `event_id`, `gateway_id`, and `timestamp`, and applies `float(value)`:

```python
{
    "sensor_id": "bme280-001",            # str, unique per physical sensor
    "measurement_type": "air_temperature",  # str, must be in the schema enum
    "value": 23.4,                          # number
    "unit": "celsius",                      # str, must be in the schema enum
}
```

### How the current sensors are wired in

BME280 (one physical read, three measurements):

```python
temperature, pressure, humidity = sensor.values   # strings such as "23.40C", "1013.20hPa", "45.10%"
return {
    "temperature_c": float(temperature.rstrip("C")),
    "humidity_pct": float(humidity.rstrip("%")),
    "pressure_hpa": float(pressure.rstrip("hPa")),
}
```

`read_all()` turns those into `air_temperature`/`celsius`, `relative_humidity`/`percent`, and `atmospheric_pressure`/`hpa`, all with `config.BME280_SENSOR_ID`. The soil sensor yields one `soil_moisture`/`raw_capacitance` measurement under `config.SOIL_SENSOR_ID`. Soil moisture is **raw capacitance, not a calibrated percentage**. If you add calibration, emit a new `unit` or `measurement_type` rather than changing what `raw_capacitance` means ([Data contracts](data-contracts.md#compatibility-rules)).

### Template for a new I²C sensor

Illustrative only; `examplesensor`, `Example`, and `0x44` are placeholders:

```python
# sensors.py
import examplesensor

EXAMPLE_ADDRESS = 0x44                                          # new


def init_example(i2c):                                          # new
    if EXAMPLE_ADDRESS not in i2c.scan():
        raise RuntimeError("Example sensor not detected")

    return examplesensor.Example(i2c=i2c, address=EXAMPLE_ADDRESS)


def init_all():
    i2c = init_i2c()

    devices = {
        "i2c": i2c,
        "bme280": None,
        "soil": None,
        "example": None,                                        # new
    }

    retry_failed(devices)
    return devices


def retry_failed(devices):
    i2c = devices["i2c"]

    # ... existing BME280 and soil blocks ...

    if devices["example"] is None:                              # new
        try:
            devices["example"] = init_example(i2c)
            print("Example sensor initialized")
        except Exception as exc:
            print("Example sensor initialization failed:", exc)


def read_all(devices):
    measurements = []

    # ... existing BME280 and soil blocks ...

    if devices["example"] is not None:                          # new
        try:
            measurements.append({
                "sensor_id": config.EXAMPLE_SENSOR_ID,
                "measurement_type": "air_temperature",
                "value": devices["example"].read_celsius(),
                "unit": "celsius",
            })
        except Exception as exc:
            print("Example sensor read failed:", exc)
            devices["example"] = None

    return measurements
```

Add the ID in both `config.py` (git-ignored, device-local) and `config.example.py` (committed template, placeholders only):

```python
EXAMPLE_SENSOR_ID = "example-001"
```

`main.py` needs no change: the new sensor is initialized at boot, retried every 30 s if it is missing, and dropped from a cycle (then retried) if a read raises.

### Failure behavior

- **At boot**, a sensor that is not detected is logged (`<sensor> initialization failed: …`) and left as `None`. The program continues with the sensors that initialized.
- **During operation**, an exception from one sensor's read is logged (`<sensor> read failed: …`), that sensor is set to `None`, and the others still publish in the same cycle. Its next initialization attempt happens within 30 s.
- **Network errors** are separate: Wi-Fi, NTP, and MQTT failures disconnect the client and retry every 5 s without restarting the program ([Architecture](architecture.md#event-flow)).
- **Pacing.** Events publish one by one, each waiting for a PUBACK. Each extra measurement lengthens the cycle slightly. Keep total read-plus-publish time well below `SAMPLE_INTERVAL_SECONDS`.

## 5. Assign IDs and measurement types

| Item | Rule |
| --- | --- |
| `sensor_id` | One per physical device, stable over time, pattern `<model>-NNN` (`bme280-001`, `soil-001`). It is part of the Redis key and the dashboard card key, so renaming it creates a new card and orphans the old one. The `sensor_id`, `gateway_id`, and `measurement_type` triple must be unique per source, or two sources overwrite each other's latest value |
| `gateway_id` | Set from `config.GATEWAY_ID` (`pi-001`). Do not change it for a new sensor |
| `measurement_type` | `snake_case`, describes the quantity, not the device |
| `unit` | Lowercase, from the schema enum |
| Two sensors of the same type | Use the same `measurement_type` and different `sensor_id`s. They get separate cards |

## Does the schema support it?

Compare the sensor's measurement type and unit with the tables in [Data contracts](data-contracts.md#measurement-types-and-units).

```text
Is measurement_type in the v2 enum, and is unit in the v2 unit enum?
├── Yes → no schema, gateway, or downstream change. Firmware only.
└── No  → schema evolution: new schema version (see below).
```

Examples with the current schema:

- A second BME280 or soil sensor: same types and units. Add a `sensor_id`, nothing else.
- `soil_temperature`/`celsius`: already in v1 and v2 but not emitted by the firmware, so adding it is firmware-only.
- A light, CO₂, or voltage sensor: new `measurement_type` and probably a new `unit`. Needs a new schema version.

### If the schema must change

Follow [Data contracts](data-contracts.md#compatibility-rules); in short:

1. Add `schemas/sensor_event.v3.schema.json` and its example (v1 and v2 stay unchanged).
2. Register version 3 in `SCHEMAS` in `gateway/ingest.py`. This is application code, so it needs review and a Pi deployment.
3. Update the schema check and tests ([Tests](#tests)).
4. Deploy the gateway first. Bump `SCHEMA_VERSION` in `main.py` only after ingest accepts v3.
5. Make a deliberate choice about units: a new unit means the dashboard's `formatValue` switch needs a case to display it well.

Changes beyond a new type and unit (new fields, key changes) can require consumer, API, and dashboard work. Use the component table in [Data contracts](data-contracts.md#what-to-check-after-a-contract-change).

## 6. Check downstream compatibility

Events travel as opaque JSON after the gateway, so verify the following.

| Component | What to confirm |
| --- | --- |
| **SQLite** | Nothing. Stored as JSON text in `event_json`. Capacity: each added measurement at a 5 s interval adds 12 rows/minute (17 280/day); acknowledged rows are deleted after 24 h |
| **Kafka** | Nothing. Same topic, key is `event_id`. No schema registry |
| **Consumer** | Event has all seven fields it checks and `value` is numeric, or it is logged as malformed and skipped (the offset is committed, so the event is not retried) |
| **Redis** | A key `greenhouse:latest:{gateway_id}:{sensor_id}:{measurement_type}` appears. Keys never expire |
| **API** | The reading appears in `GET /api/v1/sensors/latest` with a numeric `value`. A non-numeric stored value makes the whole endpoint return 503 |
| **Dashboard** | The card appears at the next 3 s poll. Check how it renders (below) |

Dashboard behavior for new data, from `App.jsx`:

- Label and order come from the `METRICS` map. Unknown types fall back to the type name with underscores replaced, capitalized, and sorted last. `atmospheric_pressure` has its own `METRICS` entry.
- `formatValue` has cases for `celsius`, `percent`, `hpa`, and `raw_capacitance`. Any other unit is shown as `String(value)` plus the unit text.
- Any reading with `unit: "percent"` also renders a 0 to 100 meter bar. That suits humidity but may be wrong for a new quantity.
- Staleness (older than 30 s) is automatic.

To polish the display, add a `METRICS` entry and a `formatValue` case. Neither is required for correct operation.

## Tests

[`.github/workflows/ci-cd.yml`](../.github/workflows/ci-cd.yml) runs `pytest tests/` in CI on every push and pull request. The suites cover the schemas, ingest, cleanup, health, the live consumer, and the API ([Deployment](deployment.md#running-the-tests-locally)). The firmware, producer, and dashboard have no automated tests; the dashboard job runs lint and build.

For a new sensor:

| Case | Test |
| --- | --- |
| Firmware-only (existing schema) | Manual: REPL read on the bench, then watch `Published:` lines and the MQTT stream ([Operations](operations.md#1-esp32-publishes-but-mqtt-shows-nothing)). MicroPython code has no automated tests |
| Schema change | Extend `tests/schemas/test_sensor_events.py` and run the validation script ([Data contracts](data-contracts.md#testing-a-schema-change-before-deployment)) |
| Changed gateway code | Add pytest tests under `tests/gateway/` |
| Changed consumer or API code | Add tests under `tests/consumers/` or `tests/api/` (these use Redis through `TEST_REDIS_URL`) |

New test files anywhere under `tests/` run in CI without workflow changes. Run the suite locally:

```bash
TEST_REDIS_URL=redis://localhost:6379/15 .venv/bin/python -m pytest tests/ -v
```

### Test the gateway with a synthetic event

Run on the Pi from the repository root after deploying any gateway change. This travels through the **real** pipeline: it reaches SQLite, Kafka, Redis, and the dashboard, so use a dedicated `sensor_id`. The example uses an existing v2 type and unit; for a new schema version, change the fields accordingly.

```bash
set -a; source .env; set +a

EVENT=$(python3 - <<'EOF'
import json, uuid
from datetime import datetime, timezone

print(json.dumps({
    "schema_version": 2,
    "event_id": str(uuid.uuid4()),
    "sensor_id": "test-001",
    "gateway_id": "pi-001",
    "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "measurement_type": "air_temperature",
    "value": 21.5,
    "unit": "celsius",
}))
EOF
)

mosquitto_pub -h localhost -p 1883 -u "$MQTT_USERNAME" -P "$MQTT_PASSWORD" \
  -t greenhouse/telemetry -q 1 -m "$EVENT"
```

Confirm `Saved:` in `journalctl -u greenhouse-ingest`, then follow the event hop by hop with [Operations](operations.md#2-mqtt-receives-but-sqlite-is-empty). Remove the test card on the serving host afterwards:

```bash
sudo docker compose exec redis redis-cli DEL greenhouse:latest:pi-001:test-001:air_temperature
```

## 7. Deploy and verify

Order matters only when the schema or gateway changes. Full procedures: [Deployment](deployment.md).

1. **Merge to `main`.** CI runs the tests and dashboard build, then deploys the gateway services to the Pi and the containers to the serving host.
2. **Gateway (only if schema or `ingest.py` changed).** Confirm the `Deploy Raspberry Pi` job succeeded, then test with a synthetic event.
3. **Dashboard (optional).** Push to the branch Netlify builds from.
4. **Firmware last.** Interrupt the device, copy changed files (new driver, `sensors.py`, `config.py`, and `main.py` if changed), reset:

```bash
source .venv/bin/activate
export ESP32_PORT=/dev/cu.usbserial-XXXXXXXX
for f in config.py bme280.py sensors.py wifi.py main.py; do
  mpremote connect "$ESP32_PORT" fs cp "firmware/esp32/$f" ":$f"
done
# also copy your new driver, for example:
# mpremote connect "$ESP32_PORT" fs cp firmware/esp32/examplesensor.py :examplesensor.py
mpremote connect "$ESP32_PORT" reset
mpremote connect "$ESP32_PORT" repl
```

Verify in order (details and commands in [Operations](operations.md#troubleshooting-flow)):

1. REPL shows `Published:` lines for the new `sensor_id`.
2. `mosquitto_sub` on the Pi shows the events.
3. `journalctl -u greenhouse-ingest` shows `Saved:` and no `Invalid event:`.
4. SQLite rows appear and `kafka_published_at` is set.
5. The consumer logs `Processed event=…`, and Redis has the new key.
6. `/api/v1/sensors/latest` and the dashboard show the reading.

### Rollback

- **Firmware.** Check out the previous commit locally, copy the earlier `sensors.py`, `config.py`, and `main.py` back to the device, and reset.
- **Schema/gateway.** Keep the new schema version registered until no device emits it and any queued or outbox events have drained.
- **Stale data.** Redis keys of a removed sensor stay on the dashboard as stale cards until deleted: `redis-cli DEL <key>`, with the key pattern shown above.
- **Dashboard.** Revert the commit; Netlify rebuilds from Git.

## Documentation updates

- Sensor tables, wiring, and addresses in [`firmware/esp32/README.md`](../firmware/esp32/README.md), including the file list and the `fs cp` commands for any new driver.
- [Data contracts](data-contracts.md) if the schema changed (versions, enums, examples).
- The sensor table in the root [README](../README.md) and the status in [Architecture](architecture.md#components).
- [`.env.example`](../.env.example) or `config.example.py` if you introduced configuration.

## Checklist

```text
Hardware
[ ] Voltage, current, and bus address checked; no address conflicts
[ ] I²C scan (or ADC read) works in the REPL on the bench
Firmware
[ ] Driver copied into firmware/esp32/ (if needed) and added to the fs cp deploy list
[ ] sensors.py: init_<sensor>(i2c) verifies the device; devices dict, retry_failed(),
    and read_all() handle it; read_all() returns {sensor_id, measurement_type, value, unit} dicts
[ ] New sensor_id added to config.py (device) and config.example.py (repo)
[ ] sensor_id unique; same type from multiple sensors uses distinct sensor_ids
Contract
[ ] measurement_type and unit in the current schema?
    [ ] Yes: no schema, gateway, consumer, or API change
    [ ] No: new schema version, SCHEMAS entry in ingest.py, SCHEMA_VERSION bump,
        data-contracts.md updated
Downstream
[ ] Dashboard: label, order, or format added only if wanted
[ ] Capacity (rows per day) acceptable
Tests and deploy
[ ] pytest tests/ passes; schema tests extended and validation script run if the schema changed
[ ] Gateway deployed and tested with a synthetic event BEFORE firmware (schema changes)
[ ] Firmware deployed; verified hop by hop to the dashboard
[ ] Test Redis keys removed; rollback path known
Docs
[ ] ESP32 README, root README, architecture, and data-contracts updated
```
