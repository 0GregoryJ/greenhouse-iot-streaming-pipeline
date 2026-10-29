# ADR 0010: Per-sensor failure isolation and non-blocking retry in the firmware

**Status:** Accepted
**Recorded:** 2026-10-28

## Context

The ESP32 runs unattended. Sensors are connected by STEMMA QT cables and can be missing at boot or fail during operation, and Wi-Fi or the broker can disappear at any time. An earlier structure initialized every sensor in one step (a missing sensor ended the program at boot) and handled a read exception for the whole cycle at once, so one bad sensor could silence the rest. A blocking sleep inside the error handler also stopped sensor retries during network outages.

## Decision

- `sensors.py` keeps a `devices` dictionary with one entry per sensor. `None` means unavailable.
- `init_all()` builds the bus and calls `retry_failed(devices)`. Each sensor initializes in its own `try`/`except`, and a failure is logged.
- `read_all(devices)` reads each available sensor in its own `try`/`except`. A failed read is logged and sets the entry to `None`.
- `main.py` calls `retry_failed()` every `SENSOR_RETRY_SECONDS` (30 s).
- Network failures (Wi-Fi, NTP, MQTT) are caught in the main loop. The client disconnects, and a retry is scheduled after `RETRY_SECONDS` (5 s) by timestamp, without a blocking sleep. If NTP fails but the clock was already synchronized, publishing continues.
- Events that were not acknowledged stay in a RAM list and are published first after reconnecting.

## Consequences

- A missing or failing sensor does not stop the others, and it recovers on its own within 30 s of becoming available.
- The device stays in one running program: no reset is needed after a wiring fix or a network outage.
- A sensor that fails is silent apart from the serial log. The pipeline does not currently report device health; a periodic heartbeat with firmware version is on the [roadmap](../../README.md#roadmap).
- Unacknowledged events live in RAM, so a power loss drops them. Optional on-device buffering is on the roadmap.
- Adding a sensor follows a fixed pattern: an `init_<sensor>(i2c)` helper, an entry in the `devices` dictionary, and a `try`/`except` block in `retry_failed()` and `read_all()` ([Adding a sensor](../adding-a-sensor.md#4-edit-sensorspy-and-configuration)).
- MicroPython code has no automated tests; verification is on the bench and through the serial log.

## Related

[`firmware/esp32/sensors.py`](../../firmware/esp32/sensors.py), [`firmware/esp32/main.py`](../../firmware/esp32/main.py), [Firmware README](../../firmware/esp32/README.md#9-reliability-and-reconnection)
