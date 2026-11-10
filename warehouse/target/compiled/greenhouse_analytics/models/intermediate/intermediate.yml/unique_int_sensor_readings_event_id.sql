
    
    

select
    event_id as unique_field,
    count(*) as n_records

from GREENHOUSE_ANALYTICS.GREENHOUSE_DBT_intermediate.int_sensor_readings
where event_id is not null
group by event_id
having count(*) > 1


