
    
    select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
  
    
    



select duplicate_record_count
from GREENHOUSE_ANALYTICS.GREENHOUSE_DBT_marts.fct_sensor_quality_daily
where duplicate_record_count is null



  
  
      
    ) dbt_internal_test