# Deployment

How each component is deployed and updated: what GitHub Actions does on every merge to `main`, and the procedures for everything else.

Related documents: [Architecture](architecture.md) · [Operations](operations.md) · [Data contracts](data-contracts.md) · [Adding a sensor](adding-a-sensor.md) · [Infrastructure README](../infrastructure/README.md) · [ESP32 firmware README](../firmware/esp32/README.md)

## Overview

| Component | How it is deployed |
| --- | --- |
| Tests and dashboard lint/build | GitHub Actions on every push and pull request ([`ci-cd.yml`](../.github/workflows/ci-cd.yml)) |
| Pi gateway services (ingest, producer) | GitHub Actions on push to `main`: pull, install requirements, restart, check `is-active` |
| Serving host (live consumer, API) | GitHub Actions on push to `main`: pull, rebuild and recreate the two containers, check `/health` |
| Pi systemd units | [`install-pi-services.sh`](../infrastructure/scripts/install-pi-services.sh), run by hand when a unit file changes |
| Kafka host | By hand: [`kafka.service`](../infrastructure/systemd/kafka.service) and the properties file |
| Redis service, Caddy, Mosquitto | By hand |
| Dashboard | Git-based deployment by Netlify |
| ESP32 firmware | `mpremote` over USB from a Mac |
| Post-deploy checks | [`verify-deployment.sh`](../infrastructure/scripts/verify-deployment.sh) (`pi`, `kafka`, `backend`), run by hand |

## Continuous integration and deployment

[`.github/workflows/ci-cd.yml`](../.github/workflows/ci-cd.yml) (workflow `CI/CD Pipeline`) defines four jobs.

| Job | Runs on | What it does |
| --- | --- | --- |
| `python-tests` | Every push and pull request | Python 3.12, a `redis:7-alpine` service, `TEST_REDIS_URL=redis://localhost:6379/15`, then `python -m pytest tests/ -v` |
| `dashboard` | Every push and pull request | Node 22 in `dashboard/`: `npm ci`, `npm run lint`, `npm run build` |
| `deploy-pi` | Push to `main`, after `python-tests` and `dashboard` pass | Deploys the gateway services to the Raspberry Pi |
| `deploy-serving-ec2` | Push to `main`, after `python-tests` and `dashboard` pass | Deploys the live consumer and API to the serving host |

Both deploy jobs use the GitHub environment `production` and a concurrency group (`greenhouse-pi-deployment`, `greenhouse-serving-deployment`) with `cancel-in-progress: false`, so a second deploy for the same host queues behind the first. The two jobs run in parallel with each other.

### What a deploy does

Each deploy job joins the tailnet as an ephemeral node tagged `tag:ci` (`tailscale/github-action`, authenticated with an OAuth client and audience, using GitHub's OIDC token), writes the deploy key and `known_hosts` entry, and connects with `ssh -o StrictHostKeyChecking=yes`.

**Pi (`deploy-pi`)**, as `greenhousepi` in `/home/greenhousepi/greenhouse-iot-streaming-pipeline`:

1. `git pull --ff-only origin main`
2. `.venv/bin/python -m pip install -r requirements/gateway.txt`
3. `sudo -n systemctl restart` for `greenhouse-ingest.service`, then for `greenhouse-kafka-producer.service`
4. `sudo -n systemctl is-active --quiet` on both services; the job fails if either is not active

The cleanup and health timers run `gateway/cleanup.py` and `gateway/health.py` from the working tree, so they pick up new code on their next run without a restart.

**Serving host (`deploy-serving-ec2`)**, as the configured user in `~/greenhouse-iot-streaming-pipeline`:

1. `git pull --ff-only origin main`
2. `docker compose up -d --build --no-deps live-consumer api`
3. `docker compose ps`
4. `curl --fail --retry 5 --retry-delay 2 http://127.0.0.1:8000/health`

Redis is not rebuilt or restarted by this job, and Caddy is not touched.

### Configuration the workflow uses

Names only; values live in GitHub and are never committed.

| Kind | Name | Purpose |
| --- | --- | --- |
| Secret | `TS_OAUTH_CLIENT_ID`, `TS_AUDIENCE` | Tailscale authentication for the runner |
| Secret | `PI_DEPLOY_SSH_KEY` | Private key for the Pi deploy user |
| Secret | `EC2_DEPLOY_SSH_KEY` | Private key for the serving host deploy user |
| Secret | `DEPLOY_KNOWN_HOSTS` | `known_hosts` lines for both hosts |
| Variable | `PI_TAILSCALE_HOST` | Tailscale name or address of the Pi |
| Variable | `EC2_TAILSCALE_HOST`, `EC2_DEPLOY_USER` | Tailscale name or address and SSH user of the serving host |

The workflow expects the following on the targets:

| Target | Expectation |
| --- | --- |
| Tailnet | The ACLs allow `tag:ci` to reach SSH on the Pi and the serving host |
| Pi | User `greenhousepi`, the repository at the path above with `.venv`, and passwordless sudo for `systemctl restart` and `systemctl is-active` on the two services |
| Serving host | The repository at `~/greenhouse-iot-streaming-pipeline` with its `.env`, and a deploy user that can run `docker compose` without `sudo` |
| Both | A clone on `main` that can fast-forward from `origin` |

### What is not deployed by CI

Pi systemd unit changes, the SQLite index migration, `.env` changes, Mosquitto and Caddy configuration, the Kafka host, the Redis service definition, the dashboard (Netlify), and the ESP32 firmware. Procedures for each follow.

### Running the tests locally

The consumer and API tests use a real Redis (database 15 of `TEST_REDIS_URL`, flushed before and after each test); the other tests need none.

```bash
docker run --rm -d --name greenhouse-test-redis -p 6379:6379 redis:7-alpine

source .venv/bin/activate
pip install -r requirements/gateway.txt -r requirements/live.txt \
            -r requirements/api.txt pytest httpx

TEST_REDIS_URL=redis://localhost:6379/15 python -m pytest tests/ -v
docker stop greenhouse-test-redis
```

| Directory | Covers |
| --- | --- |
| `tests/schemas/` | v1 and v2 JSON Schema accept and reject cases |
| `tests/gateway/` | `on_message` persistence, schema validation in ingest, cleanup, health thresholds |
| `tests/consumers/` | `parse_event`, the Redis timestamp guard, Redis failure propagation, offset commit after the Redis write |
| `tests/api/` | `/health`, `/api/v1/sensors/latest` with real, sorted, empty, and invalid stored data, Redis unavailable |

## Where things run

| Component | Host | Managed by | Source of truth in repo |
| --- | --- | --- | --- |
| Firmware | ESP32 Feather V2 | `mpremote` copy; MicroPython runs `main.py` at boot | [`firmware/esp32/`](../firmware/esp32/) |
| Mosquitto | Raspberry Pi Zero 2 W | systemd (`mosquitto`) | [`infrastructure/mosquitto/greenhouse.conf`](../infrastructure/mosquitto/greenhouse.conf) |
| Ingest, producer, cleanup, health | Raspberry Pi | systemd | [`gateway/`](../gateway/), [`infrastructure/systemd/`](../infrastructure/systemd/) |
| Kafka | EC2 #1 (`t3.small`) | systemd (`kafka`) | [`infrastructure/kafka/greenhouse.properties.example`](../infrastructure/kafka/greenhouse.properties.example), [`infrastructure/systemd/kafka.service`](../infrastructure/systemd/kafka.service) |
| Consumer, Redis, API | EC2 #2 (`t4g.small`) | Docker Compose | [`compose.yaml`](../compose.yaml) |
| Caddy | EC2 #2 | systemd (`caddy`) | [`infrastructure/caddy/caddyfile`](../infrastructure/caddy/caddyfile) (template) |
| Dashboard | Netlify | Git push | [`dashboard/`](../dashboard/) |
| Simulator | Mac (optional) | Run by hand | [`sensor_simulator/simulate.py`](../sensor_simulator/simulate.py) |

Tailscale connects the Pi, the Kafka host, the serving host, and the CI runners. AWS security groups, DNS, and instance provisioning are configured outside this repository.

## Configuration and secrets

No secret values are committed. `.env` and `firmware/esp32/config.py` are git-ignored; only templates are tracked.

| Location | Used by | Contents |
| --- | --- | --- |
| `.env` on the Pi (from [`.env.example`](../.env.example)) | `ingest.py`, `kafka_producer.py` | `MQTT_USERNAME`, `MQTT_PASSWORD`, `KAFKA_BOOTSTRAP_SERVERS`, and optional `MQTT_PORT`, `MQTT_TOPIC`, `KAFKA_TOPIC`, `KAFKA_BATCH_SIZE`, `KAFKA_RETRY_SECONDS`, `KAFKA_DELIVERY_TIMEOUT_MS` |
| `.env` on the serving host | `compose.yaml` | `KAFKA_BOOTSTRAP_SERVERS` (required), `KAFKA_TOPIC` (default `greenhouse.sensor-readings`), `KAFKA_CONSUMER_GROUP` (default `greenhouse-live-dev`), `CORS_ORIGINS` (default `http://localhost:5173`; include the dashboard origin in production) |
| `.env` on a Mac | `simulate.py` | `MQTT_HOST`, `MQTT_PORT`, `MQTT_USERNAME`, `MQTT_PASSWORD`, `MQTT_TOPIC` |
| `/etc/mosquitto/passwd` on the Pi | Mosquitto | Password hashes, created with `mosquitto_passwd` |
| `firmware/esp32/config.py` (from `config.example.py`) | ESP32 | Wi-Fi and MQTT credentials, Pi LAN address, `GATEWAY_ID`, sensor IDs, sample interval |
| `/home/ubuntu/kafka/config/greenhouse.properties` on EC2 #1 | Kafka | Copy of the example with `<TAILSCALE_IP>` replaced |
| `/etc/caddy/Caddyfile` on EC2 #2 | Caddy | Copy of the template with the real hostname |
| GitHub environment `production` | CI deploy jobs | Secrets and variables listed [above](#configuration-the-workflow-uses) |

Notes:

- `ingest.py` runs beside Mosquitto and always connects to `localhost`. It reads `MQTT_USERNAME`, `MQTT_PASSWORD`, `MQTT_PORT` (default 1883), and `MQTT_TOPIC` (default `greenhouse/telemetry`); a blank value uses the default. `MQTT_HOST` is used by the simulator only.
- `.env.example` pre-fills the application defaults (topic, consumer group, batch size, retry interval, CORS origin, MQTT topic). Credentials, `MQTT_HOST`, and `KAFKA_BOOTSTRAP_SERVERS` are blank and need values. A blank value counts as set, so delete a line rather than leaving it empty (`KAFKA_BATCH_SIZE=` fails integer parsing).
- `.env` is read when a process starts. After editing it, restart the service (`systemctl restart …`) or recreate containers (`docker compose up -d`).
- Mosquitto uses one password file; a separate account per device keeps credentials individually revocable.
- `chmod 600 .env` restricts the file to its owner.

## Raspberry Pi gateway

Repository path used by the unit files: `/home/greenhousepi/greenhouse-iot-streaming-pipeline`, user and group `greenhousepi`.

### Initial setup

```bash
git clone https://github.com/0GregoryJ/greenhouse-iot-streaming-pipeline.git
cd greenhouse-iot-streaming-pipeline

python3 -m venv .venv
.venv/bin/pip install -r requirements/gateway.txt

cp .env.example .env            # then fill in the blank values

sudo cp infrastructure/mosquitto/greenhouse.conf /etc/mosquitto/conf.d/greenhouse.conf
sudo mosquitto_passwd -c /etc/mosquitto/passwd <mqtt-user>   # -c creates the file; omit it to add more users
sudo systemctl restart mosquitto
```

Start ingest once to create `gateway/data/sensor_events.db` and the table, apply the index migration (below), then install the unit files.

For CI deploys, also grant the deploy user passwordless sudo for the restart and `is-active` commands on `greenhouse-ingest.service` and `greenhouse-kafka-producer.service`.

### Installing systemd units

```bash
sudo bash infrastructure/scripts/install-pi-services.sh
```

The script requires root and the `greenhousepi` user, runs `systemd-analyze verify` on the six units, installs them to `/etc/systemd/system/`, and runs `daemon-reload`. It does not enable or restart anything. Then:

```bash
sudo systemctl enable --now greenhouse-cleanup.timer
sudo systemctl enable --now greenhouse-health.timer
sudo systemctl enable --now greenhouse-ingest.service
sudo systemctl enable --now greenhouse-kafka-producer.service
```

To compare an installed unit with the repository copy first, use `systemctl cat greenhouse-ingest.service`.

### Database migration

Ingest creates the `sensor_events` table (`CREATE TABLE IF NOT EXISTS`). The one migration, [`002_outbox_indexes.sql`](../gateway/migrations/002_outbox_indexes.sql), adds two partial indexes and is applied by hand. The statements use `IF NOT EXISTS`, so re-running is safe:

```bash
sqlite3 gateway/data/sensor_events.db < gateway/migrations/002_outbox_indexes.sql
sqlite3 gateway/data/sensor_events.db ".indexes sensor_events"
```

A freshly created database gets the indexes when the migration is applied.

### Updating

A merge to `main` updates ingest and the producer through the `deploy-pi` job. The manual equivalent, for hotfixes or unit changes:

```bash
cd ~/greenhouse-iot-streaming-pipeline
git pull --ff-only origin main

# Only if requirements/gateway.txt changed
.venv/bin/pip install -r requirements/gateway.txt

# Restart only what changed
sudo systemctl restart greenhouse-ingest              # ingest.py or schemas/ changed
sudo systemctl restart greenhouse-kafka-producer      # kafka_producer.py or .env changed

# Only if infrastructure/systemd/ changed
sudo bash infrastructure/scripts/install-pi-services.sh

bash infrastructure/scripts/verify-deployment.sh pi
```

- Cleanup and health run as one-shot services from timers, so new code is picked up on the next run. Unit file changes need the install script.
- Restarting ingest briefly stops consumption; Mosquitto queues for the persistent session. The producer unit allows `TimeoutStopSec=90` so in-flight deliveries can finish. See [Operations](operations.md#producer-backlog).
- Mosquitto configuration changes: `sudo cp infrastructure/mosquitto/greenhouse.conf /etc/mosquitto/conf.d/greenhouse.conf && sudo systemctl restart mosquitto`. The ESP32 and ingest disconnect and reconnect.

### Rollback

The simplest rollback is to revert the bad commit on `main`: the pipeline runs the tests and redeploys the previous behavior. For an immediate manual rollback, return the working tree to a known commit and restart:

```bash
git log --oneline -5
git checkout <previous-commit>      # detached HEAD
sudo systemctl restart greenhouse-ingest greenhouse-kafka-producer
```

Run `git checkout main` afterwards so the next deploy can fast-forward. The SQLite database is not rolled back: rows written under the newer code stay, and the migration is undone with `DROP INDEX` on both indexes. A gateway older than a schema version that devices emit rejects those events.

## Kafka (EC2 #1)

Single-node KRaft broker, node ID 1, listener on a Tailscale address (port 9092), controller on `127.0.0.1:9093`, data in `/home/ubuntu/kafka-data`, 1 partition and replication factor 1 by default, 168 h retention. The template is [`greenhouse.properties.example`](../infrastructure/kafka/greenhouse.properties.example); the deployed file is `/home/ubuntu/kafka/config/greenhouse.properties`.

The service unit is [`infrastructure/systemd/kafka.service`](../infrastructure/systemd/kafka.service): user `ubuntu`, working directory `/home/ubuntu/kafka`, `KAFKA_HEAP_OPTS=-Xms512m -Xmx512m`, `Restart=on-failure` with `RestartSec=10`, `TimeoutStopSec=120`, and `LimitNOFILE=65536`.

### Initial setup

Install Kafka under `/home/ubuntu/kafka`, create the properties file from the template, format the KRaft storage once (standard Apache Kafka KRaft steps), and install the unit:

```bash
cd ~/kafka
cp ~/greenhouse-iot-streaming-pipeline/infrastructure/kafka/greenhouse.properties.example config/greenhouse.properties
nano config/greenhouse.properties                         # replace <TAILSCALE_IP>

KAFKA_CLUSTER_ID=$(bin/kafka-storage.sh random-uuid)
bin/kafka-storage.sh format -t "$KAFKA_CLUSTER_ID" -c config/greenhouse.properties

sudo cp ~/greenhouse-iot-streaming-pipeline/infrastructure/systemd/kafka.service /etc/systemd/system/kafka.service
sudo systemctl daemon-reload
sudo systemctl enable --now kafka
```

Topic: `greenhouse.sensor-readings`. `verify-deployment.sh kafka` checks that it exists. To create it explicitly:

```bash
~/kafka/bin/kafka-topics.sh --bootstrap-server "$KAFKA_BOOTSTRAP_SERVERS" \
  --create --topic greenhouse.sensor-readings --partitions 1 --replication-factor 1
```

### Updating

```bash
nano /home/ubuntu/kafka/config/greenhouse.properties      # replace <TAILSCALE_IP> in the template copy
sudo systemctl restart kafka
sudo systemctl status kafka --no-pager
```

After a unit file change, copy it as above and run `sudo systemctl daemon-reload` before restarting.

A restart interrupts producers and consumers briefly: the Pi buffers in SQLite and the consumer reconnects. Verify from the repository root on EC2 #1:

```bash
export KAFKA_BOOTSTRAP_SERVERS=<TAILSCALE_IP>:9092
bash infrastructure/scripts/verify-deployment.sh kafka
```

## Serving host (EC2 #2)

Docker Compose runs `redis` (`redis:7-alpine`, AOF persistence, volume `redis_data`), `live-consumer`, and `api` (published only on `127.0.0.1:8000`). All three use `restart: unless-stopped`. Caddy runs on the host under systemd.

### Initial setup

Requirements: Docker with Compose, Tailscale (the consumer reaches Kafka over it), Caddy, a DNS name for the API, and ports 80 and 443 open publicly. For CI deploys, the deploy user must be able to run `docker compose` without `sudo` (for example by membership in the `docker` group).

```bash
git clone https://github.com/0GregoryJ/greenhouse-iot-streaming-pipeline.git
cd greenhouse-iot-streaming-pipeline
cp .env.example .env      # set KAFKA_BOOTSTRAP_SERVERS, KAFKA_TOPIC, KAFKA_CONSUMER_GROUP, CORS_ORIGINS
sudo docker compose config --quiet
sudo docker compose up -d --build
```

### Updating containers

A merge to `main` rebuilds and recreates `live-consumer` and `api` through the `deploy-serving-ec2` job. The manual equivalent, which also applies changes to the whole stack (for example the Redis service definition):

```bash
cd <repository root>
git pull --ff-only origin main
sudo docker compose config --quiet
sudo docker compose up -d --build
sudo docker compose ps
sudo bash infrastructure/scripts/verify-deployment.sh backend
```

Compose recreates only services whose image or configuration changed. Redis data persists in the `redis_data` volume (`docker compose down -v` deletes it). Logs: [Operations](operations.md#logs).

### Caddy

The template contains a placeholder hostname, so edit the deployed file rather than copying over it. Validate, then reload:

```bash
sudo nano /etc/caddy/Caddyfile        # reverse_proxy 127.0.0.1:8000, encode zstd gzip
sudo caddy validate --config /etc/caddy/Caddyfile
sudo systemctl reload caddy
curl --fail https://api.gregoryjoshua.com/health
```

### Rollback

Revert the commit on `main` to redeploy the previous code through CI. For an immediate manual rollback, images are built on the host, so check out the previous commit and rebuild:

```bash
git checkout <previous-commit>
sudo docker compose up -d --build
sudo docker compose ps
```

Run `git checkout main` afterwards. Compose reuses cached layers where it can. Redis data is derived and can be rebuilt from Kafka ([Operations](operations.md#4-kafka-has-events-but-redis-is-empty)); changing the consumer group name replays retained events into Redis.

## Dashboard (Netlify)

The React/Vite app in [`dashboard/`](../dashboard/) is deployed from Git by Netlify to `https://greenhouse.gregoryjoshua.com`. The Netlify build settings live in the Netlify site configuration. The dashboard builds with `npm run build` (output in `dashboard/dist`), and the `dashboard` CI job runs the same lint and build on every push.

The API URL is set in [`dashboard/src/App.jsx`](../dashboard/src/App.jsx). The API lists the dashboard origin in `CORS_ORIGINS`, and `http://localhost:5173` (the default) allows local development against the production API.

```bash
cd dashboard
npm ci
npm run lint      # oxlint
npm run build     # vite build, output in dashboard/dist
npm run dev       # local dev server (Vite, port 5173 by default)
```

To deploy, push to the branch Netlify tracks and check the deploy log. To roll back, revert the commit or select a previous published deploy in Netlify.

## ESP32 firmware

Hardware setup, MicroPython flashing, and Wi-Fi/MQTT configuration are in the [firmware README](../firmware/esp32/README.md). For a routine update from the repository root on the Mac:

```bash
source .venv/bin/activate
pip install -r requirements/esp32-tools.txt        # mpremote, esptool (first time)

ls /dev/cu.usbserial*
export ESP32_PORT=/dev/cu.usbserial-XXXXXXXX

# If the program is running, interrupt it first (Ctrl+C in an open REPL).
for f in config.py bme280.py sensors.py wifi.py main.py; do
  mpremote connect "$ESP32_PORT" fs cp "firmware/esp32/$f" ":$f"
done

mpremote connect "$ESP32_PORT" fs ls
mpremote connect "$ESP32_PORT" reset
mpremote connect "$ESP32_PORT" repl            # Ctrl+] to exit
```

- The first install also needs the MQTT client library: `mpremote connect "$ESP32_PORT" mip install umqtt.simple`.
- `config.py` is git-ignored. Copy your local file, created from `config.example.py`.
- Copy only the files that changed if you prefer. Reflashing MicroPython is not needed for application changes.
- MicroPython runs `main.py` at boot. A missing sensor does not stop the program: `sensors.py` logs `<sensor> initialization failed: …` and `main.py` retries it every 30 s.
- Verify: the REPL shows `BME280 initialized`, `Soil sensor initialized`, `Connected to MQTT`, and `Published:` lines, then follow the checks in [Operations](operations.md#troubleshooting-flow).
- Rollback: check out the previous commit locally, copy the older files, and reset.

## Simulator

`sensor_simulator/simulate.py` publishes synthetic schema v1 events from a Mac to the Pi's Mosquitto: three per second (soil moisture, air temperature, relative humidity), using `MQTT_HOST`, `MQTT_PORT`, `MQTT_USERNAME`, `MQTT_PASSWORD`, and `MQTT_TOPIC` from `.env`. Dependencies are in `requirements/simulator.txt`. It validates every event against `schemas/sensor_event.v1.schema.json` (with format checking) before publishing.

```bash
source .venv/bin/activate
pip install -r requirements/simulator.txt
python sensor_simulator/simulate.py      # Ctrl+C to stop
```

Simulated events are labelled as fake by their IDs: `gateway_id` `sim-gateway-001` and `sensor_id`s `sim-soil-001` and `sim-bme280-001`. They travel through SQLite, Kafka, and Redis like real events but use their own Redis keys, so they never overwrite physical readings. While the simulator runs, the dashboard shows extra `sim-` cards next to the real ones. To remove them afterwards, delete the keys:

```bash
sudo docker compose exec redis sh -c "redis-cli --scan --pattern 'greenhouse:latest:sim-gateway-001:*' | xargs -r redis-cli DEL"
```

The IDs are the constants `SIM_GATEWAY_ID`, `SIM_SOIL_SENSOR_ID`, and `SIM_BME280_SENSOR_ID` in `simulate.py`.

## systemd units

| Unit | Host | Purpose |
| --- | --- | --- |
| `mosquitto.service` | Pi | MQTT broker |
| `greenhouse-ingest.service` | Pi | MQTT to SQLite |
| `greenhouse-kafka-producer.service` | Pi | SQLite to Kafka |
| `greenhouse-cleanup.service`, `greenhouse-cleanup.timer` | Pi | Hourly retention cleanup |
| `greenhouse-health.service`, `greenhouse-health.timer` | Pi | Health check every minute |
| `tailscaled.service` | Pi, both EC2 hosts | Private network (the producer unit orders after it; `verify-deployment.sh kafka` checks it) |
| `kafka.service` | EC2 #1 | Kafka broker ([`kafka.service`](../infrastructure/systemd/kafka.service)) |
| `caddy.service` | EC2 #2 | HTTPS reverse proxy |

## Verification

[`verify-deployment.sh`](../infrastructure/scripts/verify-deployment.sh) is read-only and exits 1 on any failure:

| Argument | Checks |
| --- | --- |
| `pi` | `mosquitto`, `greenhouse-ingest`, `greenhouse-kafka-producer` active; cleanup and health timers enabled and active; `gateway/health.py` result (a warning prints `WARN` and does not fail) |
| `kafka` | `kafka` and `tailscaled` active; `~/kafka/bin/kafka-topics.sh` present; topic listed (needs `KAFKA_BOOTSTRAP_SERVERS`) |
| `backend` | Compose config valid; `redis`, `live-consumer`, `api` containers running; `http://127.0.0.1:8000/health`; `https://api.gregoryjoshua.com/health` |

The CI deploy jobs run their own `is-active` and `/health` checks. For data flow, follow the staged checks in [Operations](operations.md#troubleshooting-flow): new rows in SQLite, a rising Kafka offset, `Processed event=…` in the consumer log, and a "Live" dashboard.

## Coordinated changes and schema migrations

Use this order for changes that touch more than one component. Rule of thumb: **the validator must accept the new data before any device emits it, and readers must cope with it before it appears.**

Because the Pi and serving deploy jobs run in parallel, a change that needs the Pi deployed before the serving host (or the reverse) is split across two merges.

| Change | Order |
| --- | --- |
| Firmware only, existing schema | Firmware |
| New sensor with an existing measurement type and unit | Firmware (dashboard polish optional) |
| New measurement type or unit (new schema version) | 1. Schema files, `ingest.py` `SCHEMAS`, tests, merge, CI green and deployed to the Pi. 2. Test with a synthetic event ([steps](adding-a-sensor.md#test-the-gateway-with-a-synthetic-event)). 3. Serving host and dashboard, if changed. 4. Firmware |
| New or removed field, changed key structure | As above, with consumer and API updated and verified **before** the firmware emits the new shape. Breaking changes use a new version and a transition period; see [Data contracts](data-contracts.md#compatibility-rules) |
| SQLite outbox change | Manual migration on the Pi. Stop ingest and producer while altering the table |
| Kafka topic or key change | Update consumers first; the topic has one partition and replication factor 1 |

Keep support for an old schema version until no device emits it and queued or outbox events have drained. Kafka retains old-version events for 168 h by default.

## Rollback summary

| Component | Method |
| --- | --- |
| Pi services | Revert on `main` (CI redeploys), or check out the previous commit and restart |
| Kafka config | Restore the previous properties file, restart |
| Containers | Revert on `main`, or check out the previous commit and `docker compose up -d --build` |
| Dashboard | Revert and push, or select a prior Netlify deploy |
| Firmware | Copy older files from Git, reset |
| Redis state | Rebuild from Kafka by changing the consumer group (limited to Kafka retention) |
