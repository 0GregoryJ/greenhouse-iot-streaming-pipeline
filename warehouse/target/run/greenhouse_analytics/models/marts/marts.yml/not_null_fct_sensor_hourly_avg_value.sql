
    
    select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
  
    
    



select avg_value
from GREENHOUSE_ANALYTICS.GREENHOUSE_DBT_marts.fct_sensor_hourly
where avg_value is null



  
  
      
    ) dbt_internal_test