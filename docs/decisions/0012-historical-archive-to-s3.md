# ADR 0012: Historical archive as gzip JSON Lines batches in S3

**Status:** Accepted
**Recorded:** 2026-11-01

## Context

Until now the pipeline kept only the latest value per sensor (Redis) and seven days of raw events (Kafka). Trend charts, daily summaries, and any warehouse or dbt work need the full history, retained indefinitely and independent of Kafka's retention. The archive should be cheap at 48 events per minute, need no new always-on database, and preserve the raw event so later loaders can reinterpret it.

## Decision

A second Kafka consumer, [`consumers/historical/consumer.py`](../../consumers/historical/consumer.py), runs under Docker Compose on the serving host in its own consumer group (`HISTORICAL_KAFKA_CONSUMER_GROUP`, default `greenhouse-historical`).

- Events are buffered per topic partition and flushed when a batch reaches `HISTORICAL_BATCH_SIZE` (240) events or is `HISTORICAL_FLUSH_SECONDS` (300) old.
- A batch is one gzip-compressed JSON Lines object: `s3://$S3_BUCKET/raw/sensor_events/year=YYYY/month=MM/day=DD/<topic>/partition=N/offsets-<first>-<last>.jsonl.gz`. The date is the UTC day the batch was opened.
- Each line is the original event unchanged, plus `_kafka_topic`, `_kafka_partition`, and `_kafka_offset`.
- The Kafka offset is committed synchronously only after `put_object` returns. Partition revocation flushes first; SIGTERM flushes pending batches within the 60 s `stop_grace_period`.
- AWS credentials come from the EC2 instance profile; nothing is stored in the repository or `.env` beyond the bucket name and region.
- A malformed message is not skipped: the consumer raises and stops at that offset.

## Consequences

- Every event accepted by the gateway is retained in S3 as the long-term record, at negligible storage cost, with no new database to operate.
- Hive-style date partitions and the Kafka lineage fields make the archive directly loadable by Snowflake external tables, Athena, or Spark, and let a loader deduplicate on `event_id` and audit gaps by offset range.
- Delivery to S3 is at-least-once per batch: a crash between upload and commit re-uploads the batch, so duplicates across objects are possible and downstream loads deduplicate on `event_id`.
- Data reaches S3 with up to five minutes of delay, which is acceptable for history and keeps the object count small (about 300 objects per day at the current rate).
- Lag on the historical group is normally non-zero (up to one batch); monitoring should allow for that.
- Because malformed messages stop the consumer, a bad message in the topic halts archiving until it is quarantined or the group offset is moved. This keeps the archive complete at the cost of availability; a quarantine path is on the [roadmap](../../README.md#roadmap).
- The instance profile requires the IMDSv2 hop limit to be 2 for containers to obtain credentials.
- Kafka retention is no longer the limit on replay for analytics; the archive is.

## Related

[Architecture](../architecture.md#event-flow), [Deployment: serving host](../deployment.md#serving-host-ec2-2), [Operations: historical consumer failures](../operations.md#historical-consumer-failures), [ADR 0006](0006-single-node-kraft-kafka-as-the-event-backbone.md)
