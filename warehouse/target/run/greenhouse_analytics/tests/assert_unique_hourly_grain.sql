
    
    select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
  SELECT
    measurement_hour_utc,
    gateway_id,
    sensor_id,
    measurement_type,
    unit,
    COUNT(*) AS row_count

FROM GREENHOUSE_ANALYTICS.GREENHOUSE_DBT_marts.fct_sensor_hourly

GROUP BY 1, 2, 3, 4, 5
HAVING COUNT(*) > 1
  
  
      
    ) dbt_internal_test