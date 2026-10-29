
"""
Sensor interface for the greenhouse ESP32.

Each sensor initializes and reads independently.
Failed sensors are retried without stopping healthy sensors.
"""

from machine import Pin, SoftI2C
import time
import bme280
import config


# Adafruit ESP32 Feather V2
STEMMA_POWER_PIN = 2
I2C_SDA_PIN = 22
I2C_SCL_PIN = 20
I2C_FREQUENCY = 100000

# Sensor I2C addresses
BME280_ADDRESS = 0x77
SOIL_ADDRESS = 0x36


def init_i2c():
    """Power the STEMMA QT connector and initialize I2C."""

    Pin(STEMMA_POWER_PIN, Pin.OUT, value=1)
    time.sleep_ms(500)

    return SoftI2C(
        sda=Pin(I2C_SDA_PIN),
        scl=Pin(I2C_SCL_PIN),
        freq=I2C_FREQUENCY,
    )


# --------------------
# BME280
# --------------------

def init_bme280(i2c):
    """Initialize the BME280 on the shared I2C bus."""

    if BME280_ADDRESS not in i2c.scan():
        raise RuntimeError("BME280 not detected")

    return bme280.BME280(
        i2c=i2c,
        address=BME280_ADDRESS,
    )


def read_bme280(sensor):
    """Read numeric temperature, humidity, and pressure."""

    temperature, pressure, humidity = sensor.values

    return {
        "temperature_c": float(temperature.rstrip("C")),
        "humidity_pct": float(humidity.rstrip("%")),
        "pressure_hpa": float(pressure.rstrip("hPa")),
    }


# --------------------
# Soil moisture
# --------------------

def init_soil(i2c):
    """Check that the seesaw soil sensor is available."""

    if SOIL_ADDRESS not in i2c.scan():
        raise RuntimeError("Soil sensor not detected")

    return i2c


def read_soil(i2c):
    """Read raw capacitive moisture using seesaw I2C."""

    i2c.writeto(SOIL_ADDRESS, bytes([0x0F, 0x10]))
    time.sleep_ms(20)

    raw = i2c.readfrom(SOIL_ADDRESS, 2)

    return (raw[0] << 8) | raw[1]


# --------------------
# Sensor management
# --------------------

def init_all():
    """
    Initialize available sensors independently.

    A failed sensor is represented by None.
    """

    i2c = init_i2c()

    devices = {
        "i2c": i2c,
        "bme280": None,
        "soil": None,
    }

    # Attempt each sensor independently.
    retry_failed(devices)

    return devices


def retry_failed(devices):
    """
    Attempt to initialize unavailable sensors.

    Called once at startup and periodically by main.py.
    """

    i2c = devices["i2c"]

    if devices["bme280"] is None:
        try:
            devices["bme280"] = init_bme280(i2c)
            print("BME280 initialized")

        except Exception as exc:
            print("BME280 initialization failed:", exc)

    if devices["soil"] is None:
        try:
            devices["soil"] = init_soil(i2c)
            print("Soil sensor initialized")

        except Exception as exc:
            print("Soil sensor initialization failed:", exc)


def read_all(devices):
    """
    Read healthy sensors independently.

    Return a flat list of measurements.
    Each measurement becomes one schema v2 MQTT event.
    """

    measurements = []

    # BME280: temperature, humidity, pressure
    if devices["bme280"] is not None:
        try:
            reading = read_bme280(devices["bme280"])

            measurements.extend([
                {
                    "sensor_id": config.BME280_SENSOR_ID,
                    "measurement_type": "air_temperature",
                    "value": reading["temperature_c"],
                    "unit": "celsius",
                },
                {
                    "sensor_id": config.BME280_SENSOR_ID,
                    "measurement_type": "relative_humidity",
                    "value": reading["humidity_pct"],
                    "unit": "percent",
                },
                {
                    "sensor_id": config.BME280_SENSOR_ID,
                    "measurement_type": "atmospheric_pressure",
                    "value": reading["pressure_hpa"],
                    "unit": "hpa",
                },
            ])

        except Exception as exc:
            print("BME280 read failed:", exc)
            devices["bme280"] = None

    # Soil sensor: raw capacitive moisture
    if devices["soil"] is not None:
        try:
            moisture = read_soil(devices["soil"])

            measurements.append({
                "sensor_id": config.SOIL_SENSOR_ID,
                "measurement_type": "soil_moisture",
                "value": moisture,
                "unit": "raw_capacitance",
            })

        except Exception as exc:
            print("Soil sensor read failed:", exc)
            devices["soil"] = None

    return measurements
