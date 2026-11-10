
    
    

select
    event_id as unique_field,
    count(*) as n_records

from GREENHOUSE_ANALYTICS.GREENHOUSE_DBT_staging.stg_sensor_events
where event_id is not null
group by event_id
having count(*) > 1


