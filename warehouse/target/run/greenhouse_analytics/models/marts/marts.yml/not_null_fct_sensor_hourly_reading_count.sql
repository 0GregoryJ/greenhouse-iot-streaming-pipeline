
    
    select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
  
    
    



select reading_count
from GREENHOUSE_ANALYTICS.GREENHOUSE_DBT_marts.fct_sensor_hourly
where reading_count is null



  
  
      
    ) dbt_internal_test