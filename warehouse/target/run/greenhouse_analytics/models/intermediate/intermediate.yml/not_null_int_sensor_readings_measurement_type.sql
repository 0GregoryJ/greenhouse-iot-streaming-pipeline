
    
    select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
  
    
    



select measurement_type
from GREENHOUSE_ANALYTICS.GREENHOUSE_DBT_intermediate.int_sensor_readings
where measurement_type is null



  
  
      
    ) dbt_internal_test