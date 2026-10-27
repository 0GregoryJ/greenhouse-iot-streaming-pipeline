
"""
Sensor abstraction for greenhouse ESP32.

Add new sensors by extending init_all() and read_all().
"""

from machine import Pin, SoftI2C
import time

import bme280
import config

# BME280 sensor (air temp, humidity, pressure)
def init_bme280():
    """Initialize the BME280 over STEMMA QT."""
    Pin(2, Pin.OUT, value=1)
    time.sleep_ms(500)

    i2c = SoftI2C(
        sda=Pin(22),
        scl=Pin(20),
        freq=100000,
    )

    if 0x77 not in i2c.scan():
        raise RuntimeError("BME280 not detected")

    return bme280.BME280(
        i2c=i2c,
        address=0x77,
    )


def read_bme280(sensor):
    """Return numerical BME280 readings."""
    temperature, pressure, humidity = sensor.values

    return {
        "temperature_c": float(temperature.rstrip("C")),
        "humidity_pct": float(humidity.rstrip("%")),
        "pressure_hpa": float(pressure.rstrip("hPa")),
    }


# Soil sensor (soil moisture)
def init_soil(i2c):
    """Verify that the soil moisture sensor is connected."""
    if 0x36 not in i2c.scan():
        raise RuntimeError("Soil sensor not detected at 0x36")

    return i2c


def read_soil(i2c):
    """Read raw capacitive soil moisture using seesaw I2C."""
    i2c.writeto(0x36, bytes([0x0F, 0x10]))
    time.sleep_ms(20)

    raw = i2c.readfrom(0x36, 2)

    return (raw[0] << 8) | raw[1]



def init_all():
    """Initialize the shared I2C bus and both sensors."""

    Pin(2, Pin.OUT, value=1)
    time.sleep_ms(500)

    i2c = SoftI2C(
        sda=Pin(22),
        scl=Pin(20),
        freq=100000,
    )

    addresses = i2c.scan()

    if 0x77 not in addresses:
        raise RuntimeError("BME280 not detected")

    if 0x36 not in addresses:
        raise RuntimeError("Soil sensor not detected")

    return {
        "bme280": bme280.BME280(i2c=i2c, address=0x77),
        "soil": i2c,
    }



def read_all(devices):
    """
    Collect all measurements as a flat list.

    Each measurement becomes a separate MQTT event.
    """
    measurements = []

    # BME280
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

    # Soil sensor
    soil_moisture = read_soil(devices["soil"])

    measurements.append({
        "sensor_id": config.SOIL_SENSOR_ID,
        "measurement_type": "soil_moisture",
        "value": soil_moisture,
        "unit": "raw_capacitance",
    })

    return measurements
