
"""
SQLite-to-Kafka publisher for the Raspberry Pi gateway.

Intended to run on the Raspberry Pi gateway continuously.

Guarantees:
- Events are selected from the local SQLite outbox.
- Only Kafka-acknowledged events are marked delivered.
- No new batch starts while a previous batch has in-flight messages.
- Failed and unconfirmed events remain in SQLite for future retries.
- Delivery is at-least-once, not exactly-once.
"""

import logging
import os
import signal
import sqlite3
import time
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from confluent_kafka import Producer
from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "gateway" / "data" / "sensor_events.db"

load_dotenv(ROOT / ".env")

KAFKA_SERVERS = os.environ["KAFKA_BOOTSTRAP_SERVERS"]
KAFKA_TOPIC = os.getenv(
    "KAFKA_TOPIC", "greenhouse.sensor-readings"
)

BATCH_SIZE = int(os.getenv("KAFKA_BATCH_SIZE", "100"))
RETRY_SECONDS = float(os.getenv("KAFKA_RETRY_SECONDS", "5"))
DELIVERY_TIMEOUT_MS = int(
    os.getenv("KAFKA_DELIVERY_TIMEOUT_MS", "60000")
)

if BATCH_SIZE < 1 or RETRY_SECONDS <= 0 or DELIVERY_TIMEOUT_MS < 1000:
    raise ValueError("Invalid Kafka producer configuration")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)

logger = logging.getLogger("greenhouse.kafka_producer")

running = True


def request_shutdown(signum, frame):
    global running
    running = False
    logger.info("Shutdown requested")


signal.signal(signal.SIGTERM, request_shutdown)
signal.signal(signal.SIGINT, request_shutdown)


def fetch_pending(conn):
    """Fetch the oldest undelivered events in a bounded batch."""
    return conn.execute(
        """
        SELECT event_id, event_json
        FROM sensor_events
        WHERE kafka_published_at IS NULL
        ORDER BY received_at, event_id
        LIMIT ?
        """,
        (BATCH_SIZE,),
    ).fetchall()


def mark_delivered(conn, event_ids):
    """Atomically mark only Kafka-acknowledged events as published."""
    if not event_ids:
        return

    published_at = datetime.now(timezone.utc).isoformat()

    with conn:
        conn.executemany(
            """
            UPDATE sensor_events
            SET kafka_published_at = ?
            WHERE event_id = ?
              AND kafka_published_at IS NULL
            """,
            [(published_at, event_id) for event_id in event_ids],
        )


def publish_batch(producer, conn, rows):
    """Publish and resolve one batch before returning.

    Delivery callbacks are scoped to this batch. The function does not
    return while messages from this batch remain in the producer queue.
    """
    acknowledged = set()
    failed = set()
    queued = 0
    enqueue_interrupted = False

    def delivery_callback(err, msg):
        event_id = msg.key().decode("utf-8")

        if err is not None:
            failed.add(event_id)
            logger.error(
                "Kafka delivery failed event_id=%s: %s",
                event_id,
                err,
            )
        else:
            acknowledged.add(event_id)

    # Enqueue a bounded group of events.
    for event_id, event_json in rows:
        if not running:
            enqueue_interrupted = True
            break

        try:
            producer.produce(
                topic=KAFKA_TOPIC,
                key=event_id.encode("utf-8"),
                value=event_json.encode("utf-8"),
                callback=delivery_callback,
            )
            queued += 1

        except BufferError:
            logger.warning("Producer queue full")
            enqueue_interrupted = True
            break

        except Exception:
            logger.exception(
                "Unable to enqueue event_id=%s",
                event_id,
            )
            enqueue_interrupted = True
            break

        # Serve completed delivery callbacks.
        producer.poll(0)

    # Wait in short intervals. Crucially, do not enqueue another
    # batch while callbacks from this batch remain outstanding.
    while producer.flush(timeout=1.0) > 0:
        if not running:
            logger.info(
                "Shutdown requested; waiting for in-flight deliveries"
            )

        # Kafka client delivery.timeout.ms bounds delivery attempts.
        # Keep waiting until every callback has received an outcome.

    # At this point all queued messages have delivery results.
    # A failed SQLite commit raises an error, leaving records pending.
    mark_delivered(conn, acknowledged)

    logger.info(
        "Batch complete: fetched=%d queued=%d acknowledged=%d "
        "failed=%d enqueue_interrupted=%s",
        len(rows),
        queued,
        len(acknowledged),
        len(failed),
        enqueue_interrupted,
    )

    return (
        len(acknowledged) == len(rows)
        and not failed
        and not enqueue_interrupted
    )


def main():
    producer = Producer({
        "bootstrap.servers": KAFKA_SERVERS,
        "security.protocol": "PLAINTEXT",
        "acks": "all",
        "enable.idempotence": True,
        "delivery.timeout.ms": DELIVERY_TIMEOUT_MS,
        "client.id": "greenhouse-pi-001",
    })

    logger.info("Kafka servers: %s", KAFKA_SERVERS)
    logger.info("Kafka topic: %s", KAFKA_TOPIC)

    # closing() ensures the SQLite connection actually closes.
    with closing(sqlite3.connect(DB_PATH, timeout=30)) as conn:
        conn.execute("PRAGMA busy_timeout = 30000")
        conn.execute("PRAGMA synchronous = FULL")

        while running:
            try:
                rows = fetch_pending(conn)

                if not rows:
                    producer.poll(0)
                    time.sleep(1)
                    continue

                success = publish_batch(producer, conn, rows)

                if not success and running:
                    logger.warning(
                        "Incomplete batch; retrying in %s seconds",
                        RETRY_SECONDS,
                    )
                    time.sleep(RETRY_SECONDS)

            except sqlite3.Error:
                logger.exception(
                    "SQLite failure; terminating for systemd recovery"
                )
                raise

    logger.info("Kafka publisher stopped")


if __name__ == "__main__":
    main()
