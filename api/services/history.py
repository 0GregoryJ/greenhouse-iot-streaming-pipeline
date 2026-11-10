
from api.repositories.snowflake import get_sensor_history


def fetch_history(sensor_id, measurement_type, period):
    points, resolution = get_sensor_history(
        sensor_id=sensor_id,
        measurement_type=measurement_type,
        period=period,
    )

    units = {point["unit"] for point in points}

    return {
        "sensor_id": sensor_id,
        "measurement_type": measurement_type,
        "period": period,
        "resolution": resolution,
        "unit": next(iter(units)) if len(units) == 1 else None,
        "count": len(points),
        "points": points,
    }
