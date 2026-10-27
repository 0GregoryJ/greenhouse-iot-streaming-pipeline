# ESP32 Sensor Firmware

MicroPython firmware for the **Adafruit ESP32 Feather V2**, responsible for collecting greenhouse environmental measurements and publishing telemetry over MQTT to a Raspberry Pi gateway.

## Overview

The ESP32 collects measurements from two physical sensors:

| Sensor | Measurement | Unit |
|---|---|---|
| BME280 | Air temperature | Celsius |
| BME280 | Relative humidity | Percent |
| BME280 | Atmospheric pressure | hPa |
| Adafruit STEMMA Soil Sensor | Soil moisture | Raw capacitance |

Both sensors communicate over a shared I²C bus. The firmware connects to Wi-Fi, synchronizes its clock using NTP, and publishes individual JSON events to the Raspberry Pi's Mosquitto MQTT broker.

```text
BME280 ────────────┐
                   ├── I²C → ESP32 Feather V2
STEMMA Soil Sensor ┘              │
                                  │ Wi-Fi / MQTT
                                  ▼
                         Raspberry Pi Gateway
                                  │
                             SQLite Outbox
                                  │
                             Apache Kafka
                                  │
                          Redis / FastAPI
                                  │
                           React Dashboard
```

## Hardware

- Adafruit ESP32 Feather V2 (ESP32-PICO-V3-02, 8 MB flash, 2 MB PSRAM)
- Adafruit BME280 temperature, humidity, and pressure sensor
- Adafruit STEMMA Soil Sensor (I²C capacitive soil-moisture sensor)
- Two STEMMA QT 4-pin JST-SH cables
- USB-C data cable
- Raspberry Pi running Mosquitto MQTT

No soldering is required for this configuration.

## 1. Install MicroPython

The ESP32 runs MicroPython rather than a conventional operating system.

**Tested firmware:** `ESP32_GENERIC-SPIRAM-20260824-v1.29.0.bin`

### Step 1: Factory reset the ESP32

Follow the [Adafruit ESP32 Feather V2 Factory Reset guide](https://learn.adafruit.com/adafruit-esp32-feather-v2/factory-reset).

1. Download the factory-reset `.bin` file provided for the ESP32 Feather V2.
2. Connect the ESP32 directly to your computer using USB-C.
3. Open the [Adafruit WebSerial ESPTool](https://adafruit.github.io/Adafruit_WebSerial_ESPTool/) in Chrome.
4. Click **Connect** and select the ESP32 serial port.
5. Click **Erase** and wait until the flash is erased successfully.
6. Select the downloaded factory-reset `.bin` file.
7. Set the flash offset to **`0x0`**.
8. Click **Program** and wait for completion.
9. Disconnect from WebSerial and press the ESP32's physical **Reset** button.

This restores the original Adafruit factory firmware. It was used successfully during initial setup after repeated command-line flashing failures.

Factory reset is a troubleshooting and recovery procedure, not a requirement for every firmware update.

### Step 2: Flash MicroPython

1. Visit the [MicroPython ESP32_GENERIC downloads page](https://micropython.org/download/ESP32_GENERIC/).
2. Under **Firmware (Support for SPIRAM / WROVER)**, download the `.bin` file for **v1.29.0 (2026-08-24)**.
3. Open the [Adafruit WebSerial ESPTool](https://adafruit.github.io/Adafruit_WebSerial_ESPTool/).
4. Connect to the ESP32.
5. Click **Erase** and wait for completion.
6. Select `ESP32_GENERIC-SPIRAM-20260824-v1.29.0.bin`.
7. Set the flash offset to **`0x1000`**.
8. Click **Program** and wait for the successful completion message.
9. Disconnect from WebSerial and press the physical **Reset** button.

**Important:** Use the standard `.bin` firmware file, not `.app-bin`, `.elf`, or `.map`. The MicroPython firmware must be flashed at offset `0x1000`, whereas Adafruit's factory-reset image uses `0x0`.

## 2. Install Development Tools

Run the following commands from the repository root on your Mac:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements/esp32-tools.txt
```

The ESP32 tooling requirements include:

- `mpremote` — interact with MicroPython and transfer files
- `esptool` — flash and inspect ESP32 firmware

### Identify the serial port

On macOS:

```bash
ls /dev/cu.usbserial*
```

The serial port used during development was:

```text
/dev/cu.usbserial-5B1E0639921
```

The port may differ on another computer.

### Verify MicroPython

```bash
mpremote connect /dev/cu.usbserial-5B1E0639921 repl
```

At the MicroPython prompt:

```python
import sys
print(sys.version)
print("Hello from greenhouse ESP32!")
```

Press `Ctrl+]` to exit the REPL.

## 3. Connect the Sensors

Both sensors use I²C and can share the Feather V2's STEMMA QT connector.

### Wiring

With the ESP32 disconnected from USB:

1. Connect the Feather V2's STEMMA QT port to either STEMMA QT connector on the BME280.
2. Connect the BME280's second STEMMA QT connector to the Adafruit STEMMA Soil Sensor.
3. Reconnect the ESP32 to USB.

No jumper wires, soldering, or breadboard are required.

### I²C configuration

| Function | GPIO / Address |
|---|---|
| STEMMA QT power enable | GPIO2 |
| I²C SDA | GPIO22 |
| I²C SCL | GPIO20 |
| I²C frequency | 100 kHz |
| BME280 address | `0x77` |
| Soil sensor address | `0x36` |

The tested MicroPython firmware successfully communicates over this configuration.

### Verify sensor detection

Connect to the MicroPython REPL and run:

```python
from machine import Pin, SoftI2C
import time

# Enable STEMMA QT power
Pin(2, Pin.OUT, value=1)
time.sleep_ms(500)

i2c = SoftI2C(
    sda=Pin(22),
    scl=Pin(20),
    freq=100000,
)

print([hex(addr) for addr in i2c.scan()])
```

Expected output:

```text
['0x36', '0x77']
```

The order may differ.

### BME280

The BME280 driver (`bme280.py`) reads:

- Air temperature in °C
- Relative humidity in %
- Atmospheric pressure in hPa

The driver returns formatted values, which `sensors.py` converts into numeric measurements.

### Soil-moisture sensor

The Adafruit STEMMA Soil Sensor uses the seesaw I²C protocol.

To test a raw capacitive reading:

```python
import time

i2c.writeto(0x36, bytes([0x0F, 0x10]))
time.sleep_ms(20)

raw = i2c.readfrom(0x36, 2)
moisture = (raw[0] << 8) | raw[1]

print("Raw soil moisture:", moisture)
```

Readings should change with the sensor's moisture exposure.

Only insert the sensing portion into soil. Keep the electronics and connector end dry.

**Soil moisture is currently reported as raw capacitance, not a calibrated percentage.** Calibration can be implemented later using dry and wet reference readings.

## 4. Firmware Structure

```text
firmware/esp32/
├── main.py
├── sensors.py
├── wifi.py
├── bme280.py
├── config.py
├── config.example.py
└── README.md
```

| File | Responsibility |
|---|---|
| `main.py` | Application lifecycle, schema v2 events, timestamps, MQTT publishing, retries |
| `sensors.py` | Shared I²C bus, sensor initialization and measurements |
| `wifi.py` | Wi-Fi connectivity and reconnection |
| `bme280.py` | MicroPython BME280 sensor driver |
| `config.py` | Local Wi-Fi, MQTT credentials, and device configuration |
| `config.example.py` | Configuration template without secrets |

The firmware is designed to be sensor-agnostic at the application level. New sensors can be integrated primarily by extending `sensors.py`.

## 5. Configure Wi-Fi and MQTT

Copy the configuration template:

```bash
cp firmware/esp32/config.example.py firmware/esp32/config.py
```

Edit `config.py`:

```python
# Wi-Fi (2.4 GHz compatible network)
WIFI_SSID = "YOUR_WIFI_SSID"
WIFI_PASSWORD = "YOUR_WIFI_PASSWORD"

# Raspberry Pi MQTT broker
MQTT_HOST = "192.168.1.100"
MQTT_PORT = 1883
MQTT_USERNAME = "YOUR_MQTT_USERNAME"
MQTT_PASSWORD = "YOUR_MQTT_PASSWORD"

MQTT_TOPIC = "greenhouse/telemetry"
MQTT_CLIENT_ID = "greenhouse-esp32-001"

# Device identification
GATEWAY_ID = "pi-001"
BME280_SENSOR_ID = "bme280-001"
SOIL_SENSOR_ID = "soil-001"

# Sampling interval
SAMPLE_INTERVAL_SECONDS = 5
```

Replace all placeholders with your own configuration.

The MQTT host must be the Raspberry Pi's LAN IP address, reachable from the ESP32 over Wi-Fi.

Find the Pi's addresses with:

```bash
hostname -I
```

Use its local Wi-Fi or Ethernet address, rather than its Tailscale address.

### Protect credentials

Ensure `.gitignore` includes:

```gitignore
firmware/esp32/config.py
```

Never commit real Wi-Fi or MQTT passwords. `config.example.py` should contain placeholders only.

Credentials are still stored as plaintext on the ESP32. The firmware is intended for a trusted local network, and the ESP32 should use a dedicated MQTT account with limited publish permissions.

## 6. Install MicroPython Dependencies

Install the MQTT client onto the ESP32:

```bash
mpremote connect /dev/cu.usbserial-5B1E0639921 mip install umqtt.simple
```

The BME280 MicroPython driver is maintained in the repository and copied to the device separately.

Unlike conventional Python applications, MicroPython does not use the Mac's virtual environment or automatically load `.env` files.

## 7. Deploy the Firmware

From the repository root on your Mac, activate the virtual environment:

```bash
source .venv/bin/activate
```

Exit any active MicroPython REPL before transferring files. If the continuous publisher is running, interrupt it with `Ctrl+C` first.

Copy the application files:

```bash
mpremote connect /dev/cu.usbserial-5B1E0639921 fs cp firmware/esp32/config.py :config.py

mpremote connect /dev/cu.usbserial-5B1E0639921 fs cp firmware/esp32/bme280.py :bme280.py

mpremote connect /dev/cu.usbserial-5B1E0639921 fs cp firmware/esp32/sensors.py :sensors.py

mpremote connect /dev/cu.usbserial-5B1E0639921 fs cp firmware/esp32/wifi.py :wifi.py

mpremote connect /dev/cu.usbserial-5B1E0639921 fs cp firmware/esp32/main.py :main.py
```

Verify the device's files:

```bash
mpremote connect /dev/cu.usbserial-5B1E0639921 fs ls
```

Restart the ESP32:

```bash
mpremote connect /dev/cu.usbserial-5B1E0639921 reset
```

Monitor the application:

```bash
mpremote connect /dev/cu.usbserial-5B1E0639921 repl
```

MicroPython automatically executes `main.py` at startup.

To update only one changed file, copy that file and restart the device. Reflashing MicroPython is not required for ordinary application changes.

## 8. Telemetry Event Schema

The firmware publishes individual JSON events using **schema v2**.

Each physical measurement produces one MQTT event.

Example atmospheric-pressure event:

```json
{
  "schema_version": 2,
  "event_id": "550e8400-e29b-41d4-a716-446655440003",
  "sensor_id": "bme280-001",
  "gateway_id": "pi-001",
  "timestamp": "2026-10-27T07:30:00Z",
  "measurement_type": "atmospheric_pressure",
  "value": 1013.2,
  "unit": "hpa"
}
```

The schema is defined in:

```text
schemas/sensor_event.v2.schema.json
```

The BME280 generates three separate events per sampling cycle:

- `air_temperature` — `celsius`
- `relative_humidity` — `percent`
- `atmospheric_pressure` — `hpa`

The soil sensor generates one additional event:

- `soil_moisture` — `raw_capacitance`

With a five-second sampling interval, the ESP32 produces approximately **48 events per minute**, or **69,120 events per day**, assuming uninterrupted operation.

Each event receives a unique UUID. Measurements taken in the same sampling cycle share a UTC timestamp.

The gateway supports version-aware schema validation so older v1 simulator events can coexist with newer v2 physical-sensor events.

## 9. Reliability and Reconnection

The application includes:

- Wi-Fi connection and reconnection handling
- NTP synchronization on startup and periodic resynchronization
- MQTT publishing with QoS 1
- Unique event IDs for downstream deduplication
- Retries for events not yet successfully published
- Continuous sampling at a configurable interval

The Raspberry Pi's SQLite outbox provides durable buffering between MQTT ingestion and Kafka delivery.

**Current limitation:** The ESP32's pending events are stored in RAM. Unsent readings can be lost during an ESP32 power failure or restart. QoS 1 provides MQTT acknowledgments but does not guarantee durable storage on the ESP32 or delivery through the entire downstream pipeline.

Persistent edge buffering, bounded network timeouts, and device-health reporting are potential future improvements.

## 10. Verify MQTT Delivery

On the Raspberry Pi, subscribe to the telemetry topic:

```bash
mosquitto_sub \
  -h localhost \
  -p 1883 \
  -u YOUR_MQTT_USERNAME \
  -P 'YOUR_MQTT_PASSWORD' \
  -t greenhouse/telemetry \
  -v
```

With the ESP32 running, this should display a continuous stream of JSON events.

### Verify SQLite ingestion

From the Raspberry Pi repository root:

```bash
sqlite3 -header -column gateway/data/sensor_events.db \
  "SELECT timestamp, sensor_id, measurement_type, value, unit
   FROM sensor_events
   ORDER BY timestamp DESC
   LIMIT 12;"
```

Expected measurements include:

```text
air_temperature
relative_humidity
atmospheric_pressure
soil_moisture
```

If events appear in MQTT but not SQLite, check the ingestion service:

```bash
sudo systemctl status greenhouse-ingest.service --no-pager
sudo journalctl -u greenhouse-ingest.service -f
```

The ingestor must have the correct versioned JSON schemas deployed before schema v2 events will be accepted.

Once accepted into SQLite, events are forwarded to Kafka and consumed by the live serving application.

## 11. Troubleshooting

| Problem | What to check |
|---|---|
| ESP32 serial port not found | USB data cable, connection, and `/dev/cu.usbserial*` |
| Firmware flashing stops early | USB connection, direct port, WebSerial flashing |
| MicroPython REPL unavailable | Correct firmware, flash offset `0x1000`, board reset |
| I²C scan returns `[]` | GPIO2 power enable, STEMMA QT cable connections |
| BME280 not detected | Expected address `0x77` |
| Soil sensor not detected | Expected address `0x36` |
| Wi-Fi connection fails | SSID, password, 2.4 GHz compatibility |
| MQTT connection fails | Pi LAN IP, Mosquitto listener, credentials, network |
| MQTT receives events but SQLite does not | Ingestor logs and schema v2 validation |
| Kafka/Redis missing events | Gateway producer status and downstream consumer validation |

## References

- [Adafruit ESP32 Feather V2 documentation](https://learn.adafruit.com/adafruit-esp32-feather-v2)
- [Adafruit Factory Reset guide](https://learn.adafruit.com/adafruit-esp32-feather-v2/factory-reset)
- [Adafruit WebSerial ESPTool](https://adafruit.github.io/Adafruit_WebSerial_ESPTool/)
- [MicroPython ESP32 firmware downloads](https://micropython.org/download/ESP32_GENERIC/)
- [MicroPython documentation](https://docs.micropython.org/)
- [Adafruit STEMMA Soil Sensor](https://learn.adafruit.com/adafruit-stemma-soil-sensor-i2c-capacitive-moisture-sensor)
