
"""Maintain the latest greenhouse sensor readings in Redis.

Kafka remains the source of the event stream.
Redis serves as a low-latency, rebuildable materialized view.

Processing contract:
1. Poll an event from Kafka.
2. Validate the fields required for the live view.
3. Atomically update Redis if the event is not older than its current state.
4. Commit the Kafka offset only after Redis acknowledges the operation.

This provides at-least-once processing with idempotent state updates.
"""

import json
import logging
import os
import signal
from datetime import datetime, timezone

import redis
from confluent_kafka import Consumer, KafkaException


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("greenhouse-live-consumer")

running = True


def shutdown(signum, frame):
    """Request a graceful shutdown after the current operation."""
    global running
    running = False


signal.signal(signal.SIGTERM, shutdown)
signal.signal(signal.SIGINT, shutdown)


# Update only if the incoming reading is at least as recent.
# Redis executes this script atomically.
UPDATE_LATEST = """
local current = redis.call("HGET", KEYS[1], "timestamp_ms")
local incoming = tonumber(ARGV[1])

if current and tonumber(current) > incoming then
    return 0
end

redis.call(
    "HSET", KEYS[1],
    "timestamp_ms", ARGV[1],
    "value", ARGV[2],
    "unit", ARGV[3],
    "timestamp", ARGV[4],
    "event_id", ARGV[5],
    "sensor_id", ARGV[6],
    "gateway_id", ARGV[7],
    "measurement_type", ARGV[8]
)

return 1
"""


def parse_event(raw_value):
    """Decode and validate the fields needed for the live view."""
    event = json.loads(raw_value)

    required = (
        "event_id",
        "sensor_id",
        "gateway_id",
        "measurement_type",
        "timestamp",
        "value",
        "unit",
    )

    for field in required:
        if field not in event:
            raise ValueError(f"Missing required field: {field}")

    # Parse the event-time timestamp, not the ingestion time.
    event_time = datetime.fromisoformat(
        event["timestamp"].replace("Z", "+00:00")
    )

    if event_time.utcoffset() is None:
        raise ValueError("Timestamp must include a timezone")

    timestamp_ms = int(
        event_time.astimezone(timezone.utc).timestamp() * 1000
    )

    if not isinstance(event["value"], (int, float)):
        raise ValueError("Measurement value must be numeric")

    return event, timestamp_ms


def write_latest(redis_client, event, timestamp_ms):
    """Update the materialized view without overwriting newer data."""
    key = (
        f"greenhouse:latest:{event['gateway_id']}:"
        f"{event['sensor_id']}:{event['measurement_type']}"
    )

    updated = redis_client.eval(
        UPDATE_LATEST,
        1,
        key,
        timestamp_ms,
        str(event["value"]),
        event["unit"],
        event["timestamp"],
        event["event_id"],
        event["sensor_id"],
        event["gateway_id"],
        event["measurement_type"],
    )

    return key, bool(updated)


def main():
    kafka_servers = os.environ["KAFKA_BOOTSTRAP_SERVERS"]
    kafka_topic = os.environ["KAFKA_TOPIC"]
    redis_host = os.environ["REDIS_HOST"]
    consumer_group = os.environ["KAFKA_CONSUMER_GROUP"]

    redis_client = redis.Redis(
        host=redis_host,
        port=6379,
        decode_responses=True,
        socket_connect_timeout=5,
        socket_timeout=5,
    )

    # Verify Redis is available before starting Kafka consumption.
    redis_client.ping()

    consumer = Consumer({
        "bootstrap.servers": kafka_servers,
        "group.id": consumer_group,
        "auto.offset.reset": "earliest",
        "enable.auto.commit": False,
        "enable.auto.offset.store": False,
        "client.id": "greenhouse-live-consumer",
    })

    consumer.subscribe([kafka_topic])
    logger.info("Subscribed to Kafka topic: %s", kafka_topic)

    try:
        while running:
            message = consumer.poll(1.0)

            if message is None:
                continue

            if message.error():
                raise KafkaException(message.error())

            # Parse the Kafka message.
            try:
                event, timestamp_ms = parse_event(message.value())

            except (ValueError, TypeError, KeyError) as exc:
                logger.warning(
                    "Skipping malformed event at partition=%s offset=%s: %s",
                    message.partition(),
                    message.offset(),
                    exc,
                )

                # Skip invalid data so it doesn't block the consumer.
                # Production systems should quarantine these events.
                consumer.commit(
                    message=message,
                    asynchronous=False,
                )
                continue

            # Write valid events to Redis.
            # Redis failures are intentionally not caught here.
            key, updated = write_latest(
                redis_client, event, timestamp_ms
            )

            # Commit only after the Redis operation succeeds.
            consumer.commit(
                message=message,
                asynchronous=False,
            )

            logger.info(
                "Processed event=%s key=%s updated=%s",
                event["event_id"],
                key,
                updated,
            )

    finally:
        logger.info("Closing Kafka consumer")
        consumer.close()
        redis_client.close()


if __name__ == "__main__":
    main()
