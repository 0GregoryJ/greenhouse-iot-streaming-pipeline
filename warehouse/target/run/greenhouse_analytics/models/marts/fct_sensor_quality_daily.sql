
  
    

create or replace transient table GREENHOUSE_ANALYTICS.GREENHOUSE_DBT_marts.fct_sensor_quality_daily
    
    
    
    
    

    as (

WITH audit_events AS (
    SELECT
        *,

        COALESCE(
            TO_DATE(
                CONVERT_TIMEZONE('UTC', measured_at)
            ),
            TO_DATE(
                CONVERT_TIMEZONE('UTC', loaded_at)
            )
        ) AS reporting_date_utc

    FROM GREENHOUSE_ANALYTICS.GREENHOUSE_DBT_intermediate.int_sensor_event_audit
),

quality_counts AS (
    SELECT
        reporting_date_utc,
        gateway_id,
        sensor_id,
        measurement_type,

        COUNT(*) AS raw_record_count,

        SUM(
            IFF(is_duplicate, 1, 0)
        ) AS duplicate_record_count,

        SUM(
            IFF(NOT is_valid, 1, 0)
        ) AS invalid_record_count,

        SUM(
            IFF(
                is_valid AND NOT is_duplicate,
                1,
                0
            )
        ) AS valid_unique_reading_count

    FROM audit_events

    GROUP BY
        reporting_date_utc,
        gateway_id,
        sensor_id,
        measurement_type
),

readings_with_previous AS (
    SELECT
        measurement_date_utc,
        gateway_id,
        sensor_id,
        measurement_type,
        measured_at_utc,

        LAG(measured_at_utc) OVER (
            PARTITION BY
                gateway_id,
                sensor_id,
                measurement_type

            ORDER BY
                measured_at_utc,
                event_id
        ) AS previous_measured_at_utc

    FROM GREENHOUSE_ANALYTICS.GREENHOUSE_DBT_intermediate.int_sensor_readings
),

daily_gaps AS (
    SELECT
        measurement_date_utc,
        gateway_id,
        sensor_id,
        measurement_type,

        MAX(
            DATEDIFF(
                'SECOND',
                previous_measured_at_utc,
                measured_at_utc
            )
        ) AS max_reading_gap_seconds

    FROM readings_with_previous

    GROUP BY
        measurement_date_utc,
        gateway_id,
        sensor_id,
        measurement_type
)

SELECT
    q.reporting_date_utc AS measurement_date_utc,

    q.gateway_id,
    q.sensor_id,
    q.measurement_type,

    q.raw_record_count,
    q.duplicate_record_count,
    q.invalid_record_count,
    q.valid_unique_reading_count,

    g.max_reading_gap_seconds

FROM quality_counts q

LEFT JOIN daily_gaps g
    ON q.reporting_date_utc = g.measurement_date_utc
   AND q.gateway_id = g.gateway_id
   AND q.sensor_id = g.sensor_id
   AND q.measurement_type = g.measurement_type
    )
;


  