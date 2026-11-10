WITH source_events AS (
    SELECT
        EVENT:event_id::VARCHAR AS event_id,
        EVENT:schema_version::INTEGER AS schema_version,
        EVENT:gateway_id::VARCHAR AS gateway_id,
        EVENT:sensor_id::VARCHAR AS sensor_id,
        TRY_TO_TIMESTAMP_TZ(EVENT:timestamp::VARCHAR) AS measured_at,
        EVENT:measurement_type::VARCHAR AS measurement_type,
        TRY_TO_DOUBLE(EVENT:value::VARCHAR) AS value,
        EVENT:unit::VARCHAR AS unit,

        EVENT:_kafka_topic::VARCHAR AS kafka_topic,
        EVENT:_kafka_partition::INTEGER AS kafka_partition,
        EVENT:_kafka_offset::BIGINT AS kafka_offset,

        SOURCE_FILE AS source_file,
        SOURCE_FILE_ROW AS source_file_row,
        LOADED_AT AS loaded_at

    FROM GREENHOUSE_ANALYTICS.RAW.SENSOR_EVENTS
),

deduplicated AS (
    SELECT *
    FROM source_events
    QUALIFY ROW_NUMBER() OVER (
        PARTITION BY event_id
        ORDER BY loaded_at DESC, source_file DESC, source_file_row DESC
    ) = 1
)

SELECT *
FROM deduplicated