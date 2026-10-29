# Architecture Decision Records

Architecture Decision Records (ADRs) capture a significant architectural decision, the reasoning behind it, and its consequences. For how the system works, see [Architecture](../architecture.md).

## Index

| ADR | Decision | Status |
| --- | --- | --- |
| [0001](0001-mqtt-for-device-ingestion.md) | MQTT with Mosquitto for device-to-gateway ingestion | Accepted |
| [0002](0002-sqlite-outbox-on-the-gateway.md) | SQLite outbox on the Raspberry Pi gateway | Accepted |
| [0003](0003-at-least-once-delivery-with-event-id-deduplication.md) | At-least-once delivery with deduplication by `event_id` | Accepted |
| [0004](0004-one-measurement-per-event.md) | One measurement per event | Accepted |
| [0005](0005-versioned-json-schemas-validated-at-the-gateway.md) | Versioned, closed JSON Schemas validated at the gateway | Accepted |
| [0006](0006-single-node-kraft-kafka-as-the-event-backbone.md) | Single-node KRaft Kafka as the event backbone | Accepted |
| [0007](0007-redis-latest-state-view-with-timestamp-guard.md) | Redis latest-state view with a timestamp-guarded update | Accepted |
| [0008](0008-tailscale-for-private-connectivity.md) | Tailscale for private connectivity between sites | Accepted |
| [0009](0009-github-actions-deployment-over-tailscale-and-ssh.md) | GitHub Actions deployment over Tailscale and SSH | Accepted |
| [0010](0010-per-sensor-failure-isolation-in-firmware.md) | Per-sensor failure isolation and non-blocking retry in the firmware | Accepted |
| [0011](0011-dashboard-polls-a-read-only-api.md) | Dashboard polls a read-only API | Accepted |

## Format

Each ADR is one Markdown file named `NNNN-short-title.md` with these sections:

| Section | Content |
| --- | --- |
| **Context** | The problem and the constraints |
| **Decision** | What was decided, stated plainly |
| **Consequences** | Resulting trade-offs, benefits, and follow-up work |
| **Status** | `Proposed`, `Accepted`, `Superseded by <ADR>`, or `Deprecated` |

Each file also records the date it was written and links to related documents and code.

## Adding or changing a decision

1. Copy the format above into the next numbered file and add it to the index.
2. Link it from the documents it affects.
3. To change a decision, write a new ADR and mark the old one `Superseded by <ADR>`. Superseded ADRs stay in the folder so the history is preserved.
