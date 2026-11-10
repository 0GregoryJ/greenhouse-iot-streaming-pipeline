
    
    select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
  
    
    



select measurement_hour_utc
from GREENHOUSE_ANALYTICS.GREENHOUSE_DBT_marts.fct_sensor_hourly
where measurement_hour_utc is null



  
  
      
    ) dbt_internal_test