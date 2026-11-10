
import os
from datetime import date, datetime, timezone

import snowflake.connector


# Only these period values are allowed.
# The table name and time interval are selected by our code,
# never supplied directly by the frontend.
PERIOD_CONFIG = {
    "24h": {
        "table": "FCT_SENSOR_HOURLY",
        "time_column": "MEASUREMENT_HOUR_UTC",
        "hours": 24,
        "resolution": "hour",
    },
    "7d": {
        "table": "FCT_SENSOR_HOURLY",
        "time_column": "MEASUREMENT_HOUR_UTC",
        "hours": 168,
        "resolution": "hour",
    },
    "30d": {
        "table": "FCT_SENSOR_DAILY",
        "time_column": "MEASUREMENT_DATE_UTC",
        "hours": 720,
        "resolution": "day",
    },
}


def get_connection():
    """Open a connection using the API service user's RSA key."""
    return snowflake.connector.connect(
        account=os.environ["SNOWFLAKE_ACCOUNT"],
        user=os.getenv("SNOWFLAKE_USER", "GREENHOUSE_API"),
        role=os.getenv("SNOWFLAKE_ROLE", "GREENHOUSE_API_READER"),
        warehouse=os.getenv("SNOWFLAKE_WAREHOUSE", "GREENHOUSE_WH"),
        database=os.getenv("SNOWFLAKE_DATABASE", "GREENHOUSE_ANALYTICS"),
        schema=os.getenv("SNOWFLAKE_SCHEMA", "GREENHOUSE_DBT_MARTS"),
        authenticator="SNOWFLAKE_JWT",
        private_key_file=os.environ["SNOWFLAKE_PRIVATE_KEY_PATH"],
        private_key_file_pwd=os.environ["SNOWFLAKE_PRIVATE_KEY_PASSPHRASE"],
        login_timeout=15,
        network_timeout=30,
    )


def get_sensor_history(sensor_id, measurement_type, period):
    """Query the appropriate mart and return timestamped readings."""

    config = PERIOD_CONFIG[period]
    table = config["table"]
    time_column = config["time_column"]
    hours = config["hours"]

    # Table and column names come from our fixed allowlist above.
    sql = f"""
        SELECT
            {time_column} AS POINT_TIME,
            AVG_VALUE,
            MIN_VALUE,
            MAX_VALUE,
            READING_COUNT,
            UNIT
        FROM GREENHOUSE_ANALYTICS.GREENHOUSE_DBT_MARTS.{table}
        WHERE SENSOR_ID = %s
          AND MEASUREMENT_TYPE = %s
          AND {time_column} >= DATEADD(
              'HOUR', -{hours}, CURRENT_TIMESTAMP()
          )
        ORDER BY {time_column}
    """

    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(sql, (sensor_id, measurement_type))
            rows = cursor.fetchall()

    points = []

    for timestamp, avg, minimum, maximum, count, unit in rows:
        # Snowflake TIMESTAMP_NTZ is stored as UTC in our dbt marts.
        if isinstance(timestamp, datetime):
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        elif isinstance(timestamp, date):
            timestamp = datetime(
                timestamp.year, timestamp.month, timestamp.day,
                tzinfo=timezone.utc,
            )

        points.append({
            "timestamp": timestamp.isoformat().replace("+00:00", "Z"),
            "avg": float(avg),
            "min": float(minimum),
            "max": float(maximum),
            "count": int(count),
            "unit": unit,
        })

    return points, config["resolution"]
