
    
    select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
  
    
    



select source_file_row
from GREENHOUSE_ANALYTICS.GREENHOUSE_DBT_intermediate.int_sensor_event_audit
where source_file_row is null



  
  
      
    ) dbt_internal_test