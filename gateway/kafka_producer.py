
"""
Kafka publisher for the Raspberry Pi gateway.

Reads sensor events from the local SQLite outbox and forwards them to
Kafka. Events remain pending until Kafka confirms delivery.

Delivery semantics:
    - At-least-once publishing from SQLite to Kafka.
    - Kafka producer idempotence enabled for supported producer retries.
    - Downstream consumers must deduplicate by event_id when necessary.

Intended to run continuously on the Raspberry Pi.
"""

import logging
import os
import signal
import sqlite3
import time
from pathlib import Path

from confluent_kafka import Producer
from dotenv import load_dotenv


# Configuration
ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "gateway" / "data" / "sensor_events.db"

load_dotenv(ROOT / ".env")

KAFKA_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS")
KAFKA_TOPIC = os.getenv("KAFKA_TOPIC", "greenhouse.sensor-readings")

BATCH_SIZE = int(os.getenv("KAFKA_BATCH_SIZE", "100"))
RETRY_SECONDS = float(os.getenv("KAFKA_RETRY_SECONDS", "5"))

if BATCH_SIZE < 1 or RETRY_SECONDS <= 0:
    raise ValueError("Batch size and retry interval must be positive.")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)

logger = logging.getLogger("greenhouse.kafka_producer")

running = True


# Shutdown handling
def request_shutdown(signum, frame):
    """Request a graceful stop after the current publish batch."""
    global running
    running = False
    logger.info("Shutdown requested")


signal.signal(signal.SIGINT, request_shutdown)
signal.signal(signal.SIGTERM, request_shutdown)


# SQLite access
def fetch_pending(conn):
    """Read the oldest events not yet acknowledged by Kafka."""
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
    """
    Mark only Kafka-acknowledged events as delivered.

    The update is committed as one SQLite transaction.
    """
    if not event_ids:
        return

    published_at = time.strftime(
        "%Y-%m-%dT%H:%M:%SZ",
        time.gmtime(),
    )

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


# Kafka publishing
def publish_batch(producer, conn, rows):
    """
    Publish one batch and record successful Kafka acknowledgments.

    Acknowledged events are marked delivered in SQLite only after
    the Kafka client's delivery callbacks have completed.
    """
    acknowledged = []
    failed = []

    def delivery_callback(err, msg):
        if err is not None:
            failed.append((msg.key(), str(err)))
            return

        acknowledged.append(msg.key().decode("utf-8"))

    queued = 0

    for event_id, event_json in rows:
        try:
            producer.produce(
                topic=KAFKA_TOPIC,
                key=event_id.encode("utf-8"),
                value=event_json.encode("utf-8"),
                callback=delivery_callback,
            )
            queued += 1

        except BufferError:
            # No message was queued for this event. Retry next cycle.
            logger.warning("Kafka producer queue full")
            break

        except Exception:
            logger.exception(
                "Unable to enqueue event_id=%s", event_id
            )
            break

        # Serve delivery callbacks while publishing.
        producer.poll(0)

    # Wait for all queued messages to receive delivery results.
    remaining = producer.flush(timeout=30)

    if remaining:
        logger.warning(
            "%s messages still unacknowledged after flush timeout",
            remaining,
        )

    mark_delivered(conn, acknowledged)

    if failed:
        logger.warning(
            "%s Kafka deliveries failed; events remain pending",
            len(failed),
        )

    logger.info(
        "Queued=%s Acknowledged=%s Failed=%s PendingCallbacks=%s",
        queued,
        len(acknowledged),
        len(failed),
        remaining,
    )

    return remaining == 0 and not failed


# Main service
def main():
    producer = Producer({
        "bootstrap.servers": KAFKA_SERVERS,
        "security.protocol": "PLAINTEXT",
        "acks": "all",
        "enable.idempotence": True,
        "client.id": "greenhouse-pi-001",
    })

    logger.info("Connecting to Kafka: %s", KAFKA_SERVERS)
    logger.info("Publishing to topic: %s", KAFKA_TOPIC)

    with sqlite3.connect(DB_PATH, timeout=30) as conn:
        conn.execute("PRAGMA busy_timeout = 30000")

        while running:
            try:
                rows = fetch_pending(conn)

                if not rows:
                    producer.poll(0)
                    time.sleep(1)
                    continue

                success = publish_batch(producer, conn, rows)

                if not success:
                    logger.warning(
                        "Batch incomplete; waiting before retry"
                    )
                    time.sleep(RETRY_SECONDS)

            except sqlite3.Error:
                logger.exception("SQLite operation failed")
                time.sleep(RETRY_SECONDS)

    # Final best-effort drain. SQLite keeps unconfirmed events.
    remaining = producer.flush(timeout=10)

    if remaining:
        logger.warning(
            "Shutting down with %s unconfirmed messages",
            remaining,
        )

    logger.info("Kafka publisher stopped")


if __name__ == "__main__":
    main()
