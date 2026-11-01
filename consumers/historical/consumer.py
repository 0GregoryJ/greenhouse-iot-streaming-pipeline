"""
Store historical sensor readings in S3 bucket.

Kafka is the source of the event stream, events are batched, serialized and compressed
into JSON lines, and uploaded to S3.

Processing contract:
1. Poll events from Kafka.
2. Validate the fields required historical storage.
3. Batch and upload.
4. Commit the Kafka offset only after S3 confirms the upload.

Failed uploads are retried.

This provides at-least-once processing with idempotent state updates.
"""

import gzip
import json
import logging
import os
import signal
import time
from datetime import datetime, timezone

import boto3
from confluent_kafka import Consumer, KafkaException, TopicPartition


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("greenhouse-historical-consumer")


BATCH_SIZE = int(os.getenv("HISTORICAL_BATCH_SIZE", "240"))
FLUSH_SECONDS = int(os.getenv("HISTORICAL_FLUSH_SECONDS", "300"))

S3_BUCKET = os.environ["S3_BUCKET"]
S3_PREFIX = os.getenv("S3_PREFIX", "raw/sensor_events").strip("/")

running = True


def shutdown(signum, frame):
    """Request graceful shutdown."""
    global running
    running = False


def parse_event(raw_value):
    """Decode an event without changing its telemetry fields."""

    event = json.loads(raw_value)

    if not isinstance(event, dict):
        raise ValueError("Event must be a JSON object")

    required = (
        "schema_version",
        "event_id",
        "sensor_id",
        "gateway_id",
        "timestamp",
        "measurement_type",
        "value",
        "unit",
    )

    for field in required:
        if field not in event:
            raise ValueError(f"Missing required field: {field}")

    return event


def make_s3_key(batch):
    """
    Build an object key identifying the Kafka offset range.

    Partition identifiers are included because offsets are
    unique within a partition, not across the entire topic.
    """

    first = batch["records"][0]
    last = batch["records"][-1]
    date = batch["created_at"].strftime("%Y/%m/%d")

    year, month, day = date.split("/")

    return (
        f"{S3_PREFIX}/"
        f"year={year}/month={month}/day={day}/"
        f"{batch['topic']}/"
        f"partition={batch['partition']}/"
        f"offsets-{first['offset']:020d}-"
        f"{last['offset']:020d}.jsonl.gz"
    )


def upload_batch(s3, batch):
    """Compress a partition batch and upload it to S3."""

    lines = []

    for record in batch["records"]:
        # Keep the original measurement and add Kafka lineage.
        output = dict(record["event"])

        output["_kafka_topic"] = batch["topic"]
        output["_kafka_partition"] = batch["partition"]
        output["_kafka_offset"] = record["offset"]

        lines.append(
            json.dumps(output, separators=(",", ":"))
        )

    data = ("\n".join(lines) + "\n").encode("utf-8")
    compressed = gzip.compress(data)

    key = make_s3_key(batch)

    s3.put_object(
        Bucket=S3_BUCKET,
        Key=key,
        Body=compressed,
        ContentType="application/x-ndjson",
        ContentEncoding="gzip",
    )

    logger.info(
        "Uploaded %s events to s3://%s/%s",
        len(batch["records"]),
        S3_BUCKET,
        key,
    )

    return key


def flush_partition(kafka, s3, batches, partition_key):
    """Upload and commit one partition's pending batch."""

    batch = batches.get(partition_key)

    if not batch or not batch["records"]:
        return

    # S3 upload must succeed before committing offsets.
    upload_batch(s3, batch)

    last_offset = batch["records"][-1]["offset"]

    kafka.commit(
        offsets=[
            TopicPartition(
                batch["topic"],
                batch["partition"],
                last_offset + 1,
            )
        ],
        asynchronous=False,
    )

    logger.info(
        "Committed partition=%s next_offset=%s",
        batch["partition"],
        last_offset + 1,
    )

    del batches[partition_key]


def flush_all(kafka, s3, batches):
    """Upload all pending partition batches."""

    for partition_key in list(batches):
        flush_partition(kafka, s3, batches, partition_key)


def main():
    """Run the historical consumer continuously."""

    kafka = Consumer({
        "bootstrap.servers": os.environ["KAFKA_BOOTSTRAP_SERVERS"],
        "group.id": os.getenv(
            "HISTORICAL_KAFKA_CONSUMER_GROUP",
            "greenhouse-historical",
        ),
        "auto.offset.reset": "earliest",
        "enable.auto.commit": False,
        "enable.auto.offset.store": False,
        "client.id": "greenhouse-historical-consumer",
    })

    s3 = boto3.client("s3")
    batches = {}

    def on_revoke(consumer, partitions):
        """Finish pending writes before losing partitions."""
        for partition in partitions:
            key = (partition.topic, partition.partition)
            flush_partition(consumer, s3, batches, key)

    def on_lost(consumer, partitions):
        """Discard buffers if partition ownership is lost."""
        for partition in partitions:
            batches.pop(
                (partition.topic, partition.partition),
                None,
            )

    kafka.subscribe(
        [os.environ["KAFKA_TOPIC"]],
        on_revoke=on_revoke,
        on_lost=on_lost,
    )

    logger.info("Historical consumer started")

    try:
        while running:
            message = kafka.poll(1.0)

            if message is not None:
                if message.error():
                    raise KafkaException(message.error())

                # Do not silently commit malformed records.
                # Investigate or quarantine them before skipping.
                event = parse_event(message.value())

                key = (message.topic(), message.partition())

                if key not in batches:
                    batches[key] = {
                        "topic": message.topic(),
                        "partition": message.partition(),
                        "created_at": datetime.now(timezone.utc),
                        "started": time.monotonic(),
                        "records": [],
                    }

                batches[key]["records"].append({
                    "offset": message.offset(),
                    "event": event,
                })

                if len(batches[key]["records"]) >= BATCH_SIZE:
                    flush_partition(kafka, s3, batches, key)

            # Flush partially filled batches based on age.
            now = time.monotonic()

            for key in list(batches):
                if (
                    now - batches[key]["started"]
                    >= FLUSH_SECONDS
                ):
                    flush_partition(kafka, s3, batches, key)

    finally:
        # Best-effort graceful shutdown. A failed upload
        # leaves offsets uncommitted for replay.
        try:
            if running is False:
                flush_all(kafka, s3, batches)
        finally:
            kafka.close()
            logger.info("Historical consumer stopped")


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    main()
