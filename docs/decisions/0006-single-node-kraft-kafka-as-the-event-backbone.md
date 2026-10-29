# ADR 0006: Single-node KRaft Kafka as the event backbone

**Status:** Accepted
**Recorded:** 2026-10-28

## Context

The Pi should publish to one durable log, and several independent readers should be able to consume it at their own pace: a live view today, and historical and streaming analytics later. Replay must be possible without involving the Pi. Cost and operational effort matter for a single-greenhouse project.

## Decision

Run one Apache Kafka broker on a dedicated EC2 instance (`t3.small`) in KRaft mode, with the broker and controller roles combined (`process.roles=broker,controller`, node ID 1). It is managed by systemd ([`kafka.service`](../../infrastructure/systemd/kafka.service)) with a 512 MB heap. Configuration is a properties template ([`greenhouse.properties.example`](../../infrastructure/kafka/greenhouse.properties.example)).

The topic is `greenhouse.sensor-readings`, with one partition, replication factor 1, and 168 h retention. The broker listens on a Tailscale address ([ADR 0008](0008-tailscale-for-private-connectivity.md)). The message key is `event_id`.

## Consequences

- The live consumer and future consumer groups read the same retained events independently. Changing the live consumer's group name replays the topic into Redis.
- KRaft removes a separate ZooKeeper service, which suits a small instance.
- One partition gives a total order in arrival sequence and simple offset handling.
- One broker with replication factor 1 means the broker's disk holds the only copy of Kafka data. Events younger than 24 hours after acknowledgment also remain in the Pi's SQLite database. A multi-broker cluster is on the [roadmap](../../README.md#roadmap).
- A broker restart pauses producers and consumers. The Pi buffers in SQLite and the consumer reconnects.
- Listeners use `PLAINTEXT`, relying on the Tailscale network for transport encryption.
- Kafka host setup (installation, KRaft storage formatting) is performed by hand until infrastructure provisioning is added.

## Related

[Architecture](../architecture.md#what-is-stored-where), [Deployment: Kafka](../deployment.md#kafka-ec2-1), [`gateway/kafka_producer.py`](../../gateway/kafka_producer.py)
