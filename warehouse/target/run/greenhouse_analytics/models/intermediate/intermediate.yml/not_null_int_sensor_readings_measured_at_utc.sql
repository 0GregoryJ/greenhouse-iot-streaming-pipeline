
    
    select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
  
    
    



select measured_at_utc
from GREENHOUSE_ANALYTICS.GREENHOUSE_DBT_intermediate.int_sensor_readings
where measured_at_utc is null



  
  
      
    ) dbt_internal_test