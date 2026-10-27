
"""
Sensor abstraction for greenhouse ESP32.

Add new sensors by extending init_all() and read_all().
"""

from machine import Pin, SoftI2C
import time

import bme280
import config


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


def init_all():
    """
    Initialize physical sensors.

    Additional sensors can be registered here later.
    """
    return {
        "bme280": init_bme280(),
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

    # Future soil-moisture sensor:
    #
    # soil = read_soil_moisture(devices["soil"])
    # measurements.append({
    #     "sensor_id": config.SOIL_SENSOR_ID,
    #     "measurement_type": "soil_moisture",
    #     "value": soil,
    #     "unit": "raw_capacitance",
    # })

    return measurements
