
  create or replace   view GREENHOUSE_ANALYTICS.GREENHOUSE_DBT_intermediate.int_sensor_readings
  
  
  
  
  as (
    

WITH staged AS (
    SELECT *
    FROM GREENHOUSE_ANALYTICS.GREENHOUSE_DBT_staging.stg_sensor_events
),

validated AS (
    SELECT
        event_id,
        schema_version,
        gateway_id,
        sensor_id,

        measured_at,

        CONVERT_TIMEZONE(
            'UTC',
            measured_at
        )::TIMESTAMP_NTZ AS measured_at_utc,

        measurement_type,
        value,
        unit,

        kafka_topic,
        kafka_partition,
        kafka_offset,
        source_file,
        source_file_row,
        loaded_at

    FROM staged

    WHERE event_id IS NOT NULL
      AND gateway_id IS NOT NULL
      AND sensor_id IS NOT NULL
      AND measured_at IS NOT NULL
      AND measurement_type IS NOT NULL
      AND value IS NOT NULL
      AND unit IS NOT NULL
),

final AS (
    SELECT
        *,

        DATE_TRUNC(
            'HOUR',
            measured_at_utc
        ) AS measurement_hour_utc,

        TO_DATE(
            measured_at_utc
        ) AS measurement_date_utc

    FROM validated
)

SELECT *
FROM final
  );

