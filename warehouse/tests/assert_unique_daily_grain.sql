SELECT
    measurement_date_utc,
    gateway_id,
    sensor_id,
    measurement_type,
    unit,
    COUNT(*) AS row_count

FROM {{ ref('fct_sensor_daily') }}

GROUP BY 1, 2, 3, 4, 5
HAVING COUNT(*) > 1
