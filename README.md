<p align="center">
  <img src="assets/header.png" alt="Greenhouse IoT Streaming Pipeline" width="100%">
</p>

<p align="center">
  <img alt="ESP32" src="https://img.shields.io/badge/ESP32-E7352C?style=for-the-badge&logo=espressif&logoColor=white">
  <img alt="Python" src="https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white">
  <img alt="Mosquitto" src="https://img.shields.io/badge/Mosquitto-3C5280?style=for-the-badge&logo=eclipsemosquitto&logoColor=white">
  <img alt="SQLite" src="https://img.shields.io/badge/SQLite-003B57?style=for-the-badge&logo=sqlite&logoColor=white">
  <img alt="Kafka" src="https://img.shields.io/badge/Kafka-231F20?style=for-the-badge&logo=apachekafka&logoColor=white">
  <img alt="Redis" src="https://img.shields.io/badge/Redis-FF4438?style=for-the-badge&logo=redis&logoColor=white">
  <img alt="FastAPI" src="https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white">
  <img alt="React" src="https://img.shields.io/badge/React-20232A?style=for-the-badge&logo=react&logoColor=61DAFB">
  <img alt="Vite" src="https://img.shields.io/badge/Vite-646CFF?style=for-the-badge&logo=vite&logoColor=white">
  <img alt="Docker" src="https://img.shields.io/badge/Docker-2496ED?style=for-the-badge&logo=docker&logoColor=white">
  <img alt="Caddy" src="https://img.shields.io/badge/Caddy-1F88C0?style=for-the-badge&logo=caddy&logoColor=white">
  <img alt="AWS" src="assets/badges/aws.svg">
  <img alt="Tailscale" src="https://img.shields.io/badge/Tailscale-242424?style=for-the-badge&logo=tailscale&logoColor=white">
  <img alt="Netlify" src="https://img.shields.io/badge/Netlify-00C7B7?style=for-the-badge&logo=netlify&logoColor=white">
  <img alt="GitHub Actions" src="https://img.shields.io/badge/GitHub%20Actions-2088FF?style=for-the-badge&logo=githubactions&logoColor=white">
</p>

# Greenhouse IoT Streaming Pipeline

An end-to-end streaming pipeline for greenhouse temperature, humidity, atmospheric pressure, and soil moisture. Sensors on an ESP32 publish readings over MQTT to a Raspberry Pi, which validates and buffers them in SQLite before forwarding them to Kafka on AWS. A live consumer keeps the latest values in Redis, and FastAPI serves them to a React dashboard, and a historical consumer is planned.

**Live:** [Dashboard](https://greenhouse.gregoryjoshua.com) · [API health](https://api.gregoryjoshua.com/health)


## Architecture

```mermaid
flowchart LR
  sensors["BME280 + soil sensor"] --> esp["ESP32<br/>MicroPython"]

  subgraph pi["Raspberry Pi"]
    mqtt["Mosquitto"] --> ingest["Ingest<br/>schema validation"]
    ingest --> sqlite[("SQLite outbox")]
    sqlite --> prod["Kafka producer"]
  end

  subgraph aws["AWS EC2"]
    kafka["Kafka"]
    consumer["Live consumer"] --> redis[("Redis")]
    redis --> api["FastAPI + Caddy"]
  end

  dash["React dashboard<br/>Netlify"]

  esp -->|"MQTT QoS 1"| mqtt
  prod -->|"Tailscale"| kafka
  kafka -->|"Tailscale"| consumer
  dash -->|"HTTPS poll"| api

  ingest -.-> dlq[("Rejected events")]
  kafka -.-> flink["Flink rolling metrics"]
  kafka -.-> snow[("Snowflake")]
  snow -.-> dbt["dbt"]

  classDef planned fill:#fff,stroke:#999,stroke-dasharray:5 5,color:#777;
  class dlq,flink,snow,dbt planned;
```

Solid boxes are implemented. Dashed boxes are on the [roadmap](#roadmap). Details: [Architecture](docs/architecture.md).

## Data flow

1. The ESP32 reads the sensors and publishes one JSON event per measurement over MQTT (QoS 1) to Mosquitto on the Pi.
2. The Pi validates each event against its schema version, commits it to SQLite, and only then acknowledges the MQTT message.
3. A producer sends pending rows to Kafka and marks a row delivered only after Kafka acknowledges it.
4. The live consumer updates the latest reading per sensor and measurement in Redis, committing its Kafka offset after the write.
5. FastAPI reads Redis, and the dashboard polls it every 3 seconds, flagging readings older than 30 seconds as stale.

Delivery is at-least-once, with deduplication by `event_id`.

## What this demonstrates

- **Durable edge buffering.** A SQLite outbox with acknowledge-after-commit ingestion keeps accepted events through Kafka and network outages. Retention cleanup removes only delivered rows.
- **Delivery semantics.** Persistent QoS 1 sessions, an acknowledged idempotent Kafka producer, manual offset commits, and idempotent Redis updates (a Lua script rejects older timestamps).
- **Versioned data contracts.** JSON Schema v1 and v2 coexist, and the gateway validates by `schema_version`.
- **Replayable streaming.** Kafka retains 7 days of events, so other consumer groups can be added.
- **Operations.** systemd services and timers, Docker Compose, a gateway health check with exit codes, and deployment verification scripts.
- **Testing and CI/CD.** pytest suites for schemas, ingest, cleanup, health, the live consumer (offset-commit ordering, Redis timestamp guard), and the API against a real Redis. GitHub Actions runs them with a dashboard lint and build, then deploys to the Pi and EC2 over Tailscale and SSH on `main`.
- **Decision records.** The reasoning behind the main design choices is written down as [ADRs](docs/decisions/README.md).
- **Networking and security basics.** Tailscale between hosts, authenticated MQTT, loopback-bound API behind Caddy HTTPS, and secrets kept out of Git.
- **Embedded work.** MicroPython firmware with shared I²C sensors, NTP time sync, per-sensor failure isolation with automatic recovery, and non-blocking network retry.

## Roadmap

Planned work, grouped by theme. Items are not scheduled.

**Reliability and hardening**

- **Rejected-event storage.** Persist invalid payloads and validation errors in a dead-letter table with bounded retention and a replay path.
- **Gateway input hardening.** Handle non-object JSON and malformed `schema_version` values without a process restart, and enforce `uuid` and `date-time` formats at the gateway so it agrees with the consumer's checks.
- **Firmware.** Socket timeouts so a stalled broker cannot block publishing, a periodic heartbeat with firmware version, optional on-device buffering, and calibrated soil moisture as a new unit.
- **Kafka.** A multi-broker cluster with replication for high availability and storage-loss protection, and a topic-level retention policy managed as code.
- **Transport security.** TLS for MQTT and Kafka, and per-device MQTT accounts with topic ACLs.
- **Redis recovery.** An automated, tested rebuild from Kafka, and expiry for retired sensors.

**Observability**

- **External alerting** for outages and a growing backlog.
- **Downstream health checks** for Kafka, the consumer, Redis, the API, and the ESP32, plus consumer-lag metrics and an end-to-end synthetic probe.
- **Centralized, structured logging.**

**CI/CD and infrastructure**

- **Deploy verification and rollback.** Run `verify-deployment.sh` and a data-freshness check after each deploy, and roll back automatically on failure. Deploy tagged container images from a registry.
- **Safer triggers.** Path filters so documentation-only changes do not redeploy, and environment approvals for production.
- **Broader deployment.** Pi systemd units, a migration runner for the SQLite database, Kafka host and Caddy configuration, and firmware releases.
- **Terraform.** EC2 instances, security groups, DNS, and host bootstrap as code.
- **Configuration as code.** Dashboard API URL from the environment (`VITE_API_URL`) and Netlify settings in the repository.

**Analytics and features**

- **Historical analytics.** A separate Kafka consumer group loading Snowflake, with dbt models and historical dashboard views.
- **Flink.** Event-time rolling-window metrics, such as 5-minute averages and moisture trends.
- **Dashboard.** Trend charts and per-sensor history.
- **More sensors.** Additional measurement types (for example light or CO₂) through new schema versions.

## Documentation

| Document | Contents |
| --- | --- |
| [Architecture](docs/architecture.md) | Components, event flow, data stores, delivery guarantees |
| [Data contracts](docs/data-contracts.md) | Schemas, validation points, safe schema evolution |
| [Adding a sensor](docs/adding-a-sensor.md) | Step-by-step guide and checklist |
| [Deployment](docs/deployment.md) | CI/CD, setup, updates, verification, and rollback for each component |
| [Operations](docs/operations.md) | Health checks, logs, troubleshooting |
| [Decision records](docs/decisions/README.md) | ADRs for the main design choices |
| [ESP32 firmware](firmware/esp32/README.md) | Hardware, MicroPython flashing, wiring, configuration |
| [Infrastructure](infrastructure/README.md) | Component-level infrastructure notes |

Configuration templates: [`.env.example`](.env.example), [`firmware/esp32/config.example.py`](firmware/esp32/config.example.py). Schemas: [`schemas/`](schemas/).

## Repository layout

```text
firmware/esp32/      MicroPython sensor firmware
sensor_simulator/    Synthetic MQTT event generator
gateway/             Raspberry Pi ingest, producer, cleanup, health, migrations
schemas/             Versioned event schemas and examples
consumers/live/      Kafka to Redis consumer
api/                 FastAPI service
dashboard/           React / Vite dashboard
infrastructure/      systemd, Mosquitto, Kafka, Caddy config and scripts
tests/               pytest suites (schemas, gateway, consumer, API)
.github/workflows/   CI and deployment workflow
requirements/        Dependencies per deployment role
compose.yaml         Consumer, Redis, and API containers
docs/                Architecture, contracts, deployment, operations
```
