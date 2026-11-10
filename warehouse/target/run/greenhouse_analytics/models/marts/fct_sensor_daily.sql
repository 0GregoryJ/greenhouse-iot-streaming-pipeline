
  
    

create or replace transient table GREENHOUSE_ANALYTICS.GREENHOUSE_DBT_marts.fct_sensor_daily
    
    
    
    
    

    as (

WITH readings AS (
    SELECT *
    FROM GREENHOUSE_ANALYTICS.GREENHOUSE_DBT_intermediate.int_sensor_readings
),

daily AS (
    SELECT
        measurement_date_utc,
        gateway_id,
        sensor_id,
        measurement_type,
        unit,

        COUNT(*) AS reading_count,

        AVG(value) AS avg_value,
        MIN(value) AS min_value,
        MAX(value) AS max_value,
        STDDEV_SAMP(value) AS stddev_value,

        MIN(measured_at_utc) AS first_measured_at_utc,
        MAX(measured_at_utc) AS last_measured_at_utc

    FROM readings

    GROUP BY
        measurement_date_utc,
        gateway_id,
        sensor_id,
        measurement_type,
        unit
)

SELECT *
FROM daily
    )
;


  