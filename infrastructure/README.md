# Infrastructure

Infrastructure configurations, deployment scripts, and operational procedures for the **Greenhouse IoT Streaming Pipeline**.

The project uses a Raspberry Pi Zero 2 W as an edge gateway, two AWS EC2 instances for event streaming and live data services, and Netlify for the public React dashboard.

Infrastructure configuration is version-controlled to support reproducible deployments, consistent service management, and easier troubleshooting.

For the complete deployment procedure, CI/CD, and rollback, see [`docs/deployment.md`](../docs/deployment.md). For monitoring and troubleshooting, see [`docs/operations.md`](../docs/operations.md).

## Architecture

```text
ESP32 Sensors / Python Simulator
              |
            MQTT
              |
              v
     Raspberry Pi Zero 2 W
     +----------------------+
     | Mosquitto            |
     | MQTT Ingestion       |
     | SQLite Outbox        |
     | Kafka Producer       |
     +----------------------+
              |
        Tailscale VPN
              |
              v
       AWS EC2 #1
     +----------------------+
     | Apache Kafka         |
     | Single-node KRaft    |
     +----------------------+
              |
        Tailscale VPN
              |
              v
       AWS EC2 #2
     +----------------------+
     | Kafka Live Consumer  |
     | Redis                |
     | FastAPI              |
     | Caddy (HTTPS)        |
     +----------------------+
              |
            HTTPS
              |
              v
      Netlify React Dashboard
```

The Raspberry Pi provides durable local event buffering, Kafka decouples event production from consumption, and Redis maintains the latest sensor state for low-latency dashboard access.

## Directory Structure

```text
infrastructure/
├── caddy/
│   └── caddyfile
├── kafka/
│   └── greenhouse.properties.example
├── mosquitto/
│   └── greenhouse.conf
├── systemd/
│   ├── greenhouse-ingest.service
│   ├── greenhouse-kafka-producer.service
│   ├── greenhouse-cleanup.service
│   ├── greenhouse-cleanup.timer
│   ├── greenhouse-health.service
│   ├── greenhouse-health.timer
│   └── kafka.service
├── scripts/
│   ├── install-pi-services.sh
│   └── verify-deployment.sh
└── README.md
```

The Pi units are installed by `scripts/install-pi-services.sh`. `kafka.service` runs on EC2 #1 and is installed by hand. Caddy's template is named `caddyfile` here and is deployed as `/etc/caddy/Caddyfile`.

## Deployment Environments

| Host | Components | Management |
|---|---|---|
| Raspberry Pi Zero 2 W | Mosquitto, MQTT ingestion, SQLite, Kafka producer | systemd |
| AWS EC2 #1 (`t3.small`) | Apache Kafka broker | systemd |
| AWS EC2 #2 (`t4g.small`) | Kafka consumer, Redis, FastAPI | Docker Compose |
| AWS EC2 #2 | Caddy reverse proxy | systemd |
| Netlify | React/Vite dashboard | Git-based deployment |

## 1. Raspberry Pi Gateway

The Raspberry Pi acts as an edge gateway, receiving MQTT telemetry, validating events, persisting them to SQLite, and publishing them to Kafka.

### Mosquitto Configuration

Repository configuration:

`mosquitto/greenhouse.conf`

Deployed configuration:

`/etc/mosquitto/conf.d/greenhouse.conf`

The broker listens on port `1883` and requires authenticated MQTT clients.

Password hashes are stored in `/etc/mosquitto/passwd` on the Pi and must not be committed to Git.

### Gateway Services

| Service | Responsibility |
|---|---|
| `greenhouse-ingest.service` | Validate incoming MQTT events and persist them to SQLite |
| `greenhouse-kafka-producer.service` | Publish pending SQLite records to Kafka |
| `greenhouse-cleanup.timer` | Periodically delete acknowledged records past retention |
| `greenhouse-health.timer` | Monitor ingestion freshness, delivery backlog, and disk usage |

The SQLite outbox supports retrying failed Kafka deliveries without losing successfully persisted measurements.

Pending events are retained until Kafka acknowledges delivery. Delivery is at-least-once, so downstream consumers deduplicate on `event_id`.

### Installing systemd Units

Run from the repository root on the Raspberry Pi:

```bash
sudo bash infrastructure/scripts/install-pi-services.sh
```

The script validates and installs the Pi systemd unit files, then reloads systemd.

It does not automatically restart or enable running services.

Enable timers and services:

```bash
sudo systemctl enable --now greenhouse-cleanup.timer
sudo systemctl enable --now greenhouse-health.timer
sudo systemctl enable --now greenhouse-ingest.service
sudo systemctl enable --now greenhouse-kafka-producer.service
```

To compare an installed unit with the repository copy, use `systemctl cat greenhouse-ingest.service`.

Restart gateway applications when appropriate:

```bash
sudo systemctl restart greenhouse-ingest
sudo systemctl restart greenhouse-kafka-producer
```

### Verify Gateway Deployment

```bash
bash infrastructure/scripts/verify-deployment.sh pi
```

View service logs:

```bash
journalctl -u greenhouse-ingest -f
journalctl -u greenhouse-kafka-producer -f
```

## 2. Apache Kafka — AWS EC2 #1

Kafka runs on a dedicated Ubuntu EC2 instance as a single-node KRaft broker.

### Configuration

Repository template:

`kafka/greenhouse.properties.example`

Deployed configuration:

`/home/ubuntu/kafka/config/greenhouse.properties`

The template uses a placeholder for the EC2 instance's private Tailscale IP address.

Before deployment, replace the placeholder with the instance's Tailscale address.

### Broker Settings

| Setting | Value |
|---|---|
| Broker/controller roles | Combined KRaft node |
| Node ID | `1` |
| Broker listener | Tailscale IP, port `9092` |
| Controller listener | Localhost, port `9093` |
| Kafka data directory | `/home/ubuntu/kafka-data` |
| Default partitions | `1` |
| Default replication factor | `1` |
| Default retention | 168 hours (7 days) |

Kafka's data directory is intended to reside on the EC2 instance's persistent EBS-backed filesystem.

### Topic

The telemetry topic is:

`greenhouse.sensor-readings`

The topic uses a single partition and replication factor one.

### Service Management

The broker runs as the systemd unit [`systemd/kafka.service`](systemd/kafka.service), installed as `/etc/systemd/system/kafka.service` (user `ubuntu`, 512 MB heap, `Restart=on-failure`):

```bash
sudo cp infrastructure/systemd/kafka.service /etc/systemd/system/kafka.service
sudo systemctl daemon-reload
sudo systemctl enable --now kafka
```

```bash
sudo systemctl status kafka
sudo journalctl -u kafka -f
```

Inspect the running Kafka configuration:

```bash
sudo systemctl show kafka -p ExecStart --no-pager
```

### Verify Kafka Deployment

```bash
export KAFKA_BOOTSTRAP_SERVERS=YOUR_TAILSCALE_IP:9092

bash infrastructure/scripts/verify-deployment.sh kafka
```

## 3. Live Backend — AWS EC2 #2

The live backend consists of three Docker Compose services.

| Service | Responsibility |
|---|---|
| `live-consumer` | Consume Kafka telemetry and update Redis |
| `redis` | Store the latest measurement per sensor and measurement type |
| `api` | Expose read-only FastAPI endpoints |

Docker Compose configuration is maintained at the repository root:

`compose.yaml`

### Deployment

A merge to `main` rebuilds and recreates `live-consumer` and `api` through GitHub Actions. To deploy the whole stack by hand, run from the repository root on EC2 #2:

```bash
sudo docker compose config
sudo docker compose up -d --build
sudo docker compose ps
```

### Logs

```bash
sudo docker compose logs -f live-consumer
sudo docker compose logs -f api
```

### API Verification

```bash
curl --fail http://127.0.0.1:8000/health
```

Redis communicates with other services through the internal Docker network and is not publicly exposed.

FastAPI is bound to the EC2 instance's loopback interface.

## 4. HTTPS and Caddy

Caddy runs directly on EC2 #2 as a systemd-managed reverse proxy.

Repository template (contains a placeholder hostname):

`caddy/caddyfile`

Deployed configuration:

`/etc/caddy/Caddyfile`

Public API:

`https://api.gregoryjoshua.com`

Caddy terminates HTTPS and forwards requests to FastAPI on `127.0.0.1:8000`.

### Validate and Reload

```bash
sudo caddy validate --config /etc/caddy/Caddyfile
sudo systemctl reload caddy
```

Verify the public endpoint:

```bash
curl --fail https://api.gregoryjoshua.com/health
```

The React dashboard is hosted separately through Netlify.

## 5. Deployment Scripts

Deployment utilities are stored in `infrastructure/scripts/`.

### `install-pi-services.sh`

Installs version-controlled systemd service and timer files on the Raspberry Pi.

```bash
sudo bash infrastructure/scripts/install-pi-services.sh
```

The script:

- Checks that it is running with root privileges.
- Verifies the expected Raspberry Pi user exists.
- Checks required unit files.
- Validates systemd configuration.
- Installs service and timer definitions.
- Reloads the systemd manager.

It does not automatically restart existing applications.

### `verify-deployment.sh`

Performs read-only operational checks for the specified deployment environment.

| Command | Environment |
|---|---|
| `bash infrastructure/scripts/verify-deployment.sh pi` | Raspberry Pi |
| `bash infrastructure/scripts/verify-deployment.sh kafka` | Kafka EC2 |
| `sudo bash infrastructure/scripts/verify-deployment.sh backend` | Live backend EC2 |

Checks include service status, timers, gateway health, Kafka topic availability, running containers, and API availability.

Verification is intended to complement automated tests, not replace them.

## 6. Networking and Security

The deployment uses Tailscale for private connectivity between the gateway and Kafka infrastructure.

| Port | Service | Access |
|---|---|---|
| 1883 | Mosquitto MQTT | Trusted clients |
| 9092 | Kafka | Tailscale |
| 6379 | Redis | Internal Docker network |
| 8000 | FastAPI | Localhost |
| 443 | Caddy HTTPS | Public |
| 80 | Caddy HTTP / certificate validation | Public |
| 22 | SSH | Restricted administration |

Security practices:

- Do not commit credentials or `.env` files containing secrets.
- Keep MQTT password databases outside Git.
- Do not expose Kafka or Redis to the public internet.
- Restrict AWS security groups to required traffic.
- Keep Tailscale authentication keys private.
- Validate configurations before deploying changes.
- Use least-privilege service accounts where practical.

Kafka currently uses plaintext communication within the private Tailscale network. Tailscale provides encrypted transport between participating nodes.

## 7. Monitoring and Maintenance

### SQLite Retention

The gateway removes Kafka-acknowledged records older than 24 hours.

Pending events are excluded from time-based cleanup.

### Gateway Health Monitoring

The health-check script reports:

- Total stored records.
- Pending Kafka event count.
- Oldest pending event age.
- Latest ingestion timestamp.
- Latest Kafka delivery timestamp.
- SQLite database size.
- Disk utilization.

The health check is executed periodically through a systemd timer.

### Recovery

The gateway's SQLite outbox buffers events during Kafka outages.

Once Kafka becomes available, pending events are retried.

Redis holds a derived latest-state view. To rebuild it, replay Kafka with a new consumer group (see [`docs/operations.md`](../docs/operations.md#4-kafka-has-events-but-redis-is-empty)).

### Logs

| Component | Log access |
|---|---|
| Gateway ingestion | `journalctl -u greenhouse-ingest -f` |
| Kafka producer | `journalctl -u greenhouse-kafka-producer -f` |
| Kafka broker | `journalctl -u kafka -f` |
| Live consumer | `docker compose logs -f live-consumer` |
| FastAPI | `docker compose logs -f api` |
| Caddy | `journalctl -u caddy -f` |

## 8. Development and Deployment Workflow

Infrastructure and application changes follow this process:

1. Implement changes on a feature branch.
2. Run relevant local tests (`python -m pytest tests/`).
3. Push to GitHub; Actions runs the pytest suite and the dashboard lint and build.
4. Review and merge to `main`.
5. On `main`, GitHub Actions deploys over Tailscale and SSH: the Pi's ingest and producer services are restarted, and the serving host's `live-consumer` and `api` containers are rebuilt.
6. Apply what CI does not deploy by hand: Pi systemd units, the SQLite migration, Kafka host changes, Caddy, and the ESP32 firmware (see [`docs/deployment.md`](../docs/deployment.md)).
7. Run the corresponding deployment verification script.
8. Confirm service health and data freshness.

Tests live in `tests/`, and the workflow is [`.github/workflows/ci-cd.yml`](../.github/workflows/ci-cd.yml).

## 9. Future Improvements

The roadmap in the root [README](../README.md#roadmap) lists planned infrastructure work, including Terraform-based provisioning, deploy verification and rollback in CI/CD, centralized observability, and a multi-broker Kafka cluster.
