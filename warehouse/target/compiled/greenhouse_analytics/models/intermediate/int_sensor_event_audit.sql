

WITH source_events AS (
    SELECT
        EVENT:event_id::VARCHAR AS event_id,
        EVENT:gateway_id::VARCHAR AS gateway_id,
        EVENT:sensor_id::VARCHAR AS sensor_id,

        TRY_TO_TIMESTAMP_TZ(
            EVENT:timestamp::VARCHAR
        ) AS measured_at,

        EVENT:measurement_type::VARCHAR AS measurement_type,

        TRY_TO_DOUBLE(
            EVENT:value::VARCHAR
        ) AS value,

        EVENT:unit::VARCHAR AS unit,

        EVENT:_kafka_topic::VARCHAR AS kafka_topic,
        EVENT:_kafka_partition::INTEGER AS kafka_partition,
        EVENT:_kafka_offset::BIGINT AS kafka_offset,

        source_file,
        source_file_row,
        loaded_at

    FROM GREENHOUSE_ANALYTICS.RAW.SENSOR_EVENTS
),

ranked AS (
    SELECT
        *,

        ROW_NUMBER() OVER (
            PARTITION BY event_id
            ORDER BY
                loaded_at DESC,
                source_file DESC,
                source_file_row DESC
        ) AS event_rank

    FROM source_events
),

audited AS (
    SELECT
        *,

        IFF(
            event_id IS NOT NULL
            AND event_rank > 1,
            TRUE,
            FALSE
        ) AS is_duplicate,

        IFF(
            event_id IS NOT NULL
            AND gateway_id IS NOT NULL
            AND sensor_id IS NOT NULL
            AND measured_at IS NOT NULL
            AND measurement_type IS NOT NULL
            AND value IS NOT NULL
            AND unit IS NOT NULL,
            TRUE,
            FALSE
        ) AS is_valid

    FROM ranked
)

SELECT
    event_id,
    gateway_id,
    sensor_id,
    measured_at,
    measurement_type,
    value,
    unit,

    kafka_topic,
    kafka_partition,
    kafka_offset,

    source_file,
    source_file_row,
    loaded_at,

    is_duplicate,
    is_valid

FROM audited