
    
    select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
  
    
    



select is_duplicate
from GREENHOUSE_ANALYTICS.GREENHOUSE_DBT_intermediate.int_sensor_event_audit
where is_duplicate is null



  
  
      
    ) dbt_internal_test