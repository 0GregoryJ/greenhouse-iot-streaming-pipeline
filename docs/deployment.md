# Deployment

How each component is deployed and updated today. Every deployment step here is **manual**. Planned automation is called out explicitly.

Related documents: [Architecture](architecture.md) · [Operations](operations.md) · [Data contracts](data-contracts.md) · [Adding a sensor](adding-a-sensor.md) · [Infrastructure README](../infrastructure/README.md) · [ESP32 firmware README](../firmware/esp32/README.md)

## Current state and planned automation

| Capability | Status |
| --- | --- |
| Automated tests on push and pull request | **Implemented**: [`.github/workflows/tests.yml`](../.github/workflows/tests.yml) runs `pytest tests/gateway/` on Python 3.12 |
| Install Pi systemd units | **Implemented, manual**: [`install-pi-services.sh`](../infrastructure/scripts/install-pi-services.sh) copies unit files and reloads systemd. It does not restart or enable anything |
| Read-only post-deploy checks | **Implemented, manual**: [`verify-deployment.sh`](../infrastructure/scripts/verify-deployment.sh) (`pi`, `kafka`, `backend`) |
| Deploying code to the Pi or EC2 hosts | **Manual**: SSH in, `git pull`, restart services or rebuild containers |
| Dashboard | Git-based deployment by Netlify (settings are not in this repository) |
| ESP32 firmware | **Manual**: `mpremote` over USB from a Mac |
| Build, validation, and deployment workflows; automated rollback; infrastructure provisioning | **Planned**. Nothing exists in the repository |

The planned work is to reduce manual deployments: a repeatable process with tests as a gate, safeguards (such as post-deploy health checks), and a defined rollback path for the Pi and EC2 services. The design is **TBD**. Until then, follow the manual procedures below.

## Where things run

| Component | Host | Managed by | Source of truth in repo |
| --- | --- | --- | --- |
| Firmware | ESP32 Feather V2 | `mpremote` copy; MicroPython runs `main.py` at boot | [`firmware/esp32/`](../firmware/esp32/) |
| Mosquitto | Raspberry Pi Zero 2 W | systemd (`mosquitto`) | [`infrastructure/mosquitto/greenhouse.conf`](../infrastructure/mosquitto/greenhouse.conf) |
| Ingest, producer, cleanup, health | Raspberry Pi | systemd | [`gateway/`](../gateway/), [`infrastructure/systemd/`](../infrastructure/systemd/) |
| Kafka | EC2 #1 (`t3.small`) | systemd (`kafka`; the unit file is not in the repo) | [`infrastructure/kafka/greenhouse.properties.example`](../infrastructure/kafka/greenhouse.properties.example) |
| Consumer, Redis, API | EC2 #2 (`t4g.small`) | Docker Compose | [`compose.yaml`](../compose.yaml) |
| Caddy | EC2 #2 | systemd (`caddy`) | [`infrastructure/caddy/caddyfile`](../infrastructure/caddy/caddyfile) (template) |
| Dashboard | Netlify | Git push | [`dashboard/`](../dashboard/) |
| Simulator | Mac (optional) | Run by hand | [`sensor_simulator/simulate.py`](../sensor_simulator/simulate.py) |

Tailscale connects the Pi, the Kafka host, and the serving host. Its installation and authentication are outside this repository. AWS security groups, DNS, and instance provisioning are not in the repository either.

## Configuration and secrets

No secret values are committed. `.env` and `firmware/esp32/config.py` are git-ignored; only templates are tracked.

| Location | Used by | Contents |
| --- | --- | --- |
| `.env` on the Pi (from [`.env.example`](../.env.example)) | `ingest.py`, `kafka_producer.py` | `MQTT_USERNAME`, `MQTT_PASSWORD`, `KAFKA_BOOTSTRAP_SERVERS`, and optional `KAFKA_TOPIC`, `KAFKA_BATCH_SIZE`, `KAFKA_RETRY_SECONDS`, `KAFKA_DELIVERY_TIMEOUT_MS` |
| `.env` on the serving host | `compose.yaml` | `KAFKA_BOOTSTRAP_SERVERS` (required), `KAFKA_TOPIC` (default `greenhouse.sensor-readings`), `KAFKA_CONSUMER_GROUP` (default `greenhouse-live-dev`), `CORS_ORIGINS` (default `http://localhost:5173`; must include the dashboard origin in production) |
| `.env` on a Mac | `simulate.py` | `MQTT_HOST`, `MQTT_PORT`, `MQTT_USERNAME`, `MQTT_PASSWORD`, `MQTT_TOPIC` |
| `/etc/mosquitto/passwd` on the Pi | Mosquitto | Password hashes, created with `mosquitto_passwd`. Never committed |
| `firmware/esp32/config.py` (from `config.example.py`) | ESP32 | Wi-Fi and MQTT credentials, Pi LAN address, `GATEWAY_ID`, sensor IDs, sample interval. Stored in plaintext on the device |
| `/home/ubuntu/kafka/config/greenhouse.properties` on EC2 #1 | Kafka | Copy of the example with `<TAILSCALE_IP>` replaced |
| `/etc/caddy/Caddyfile` on EC2 #2 | Caddy | Copy of the template with the real hostname |

Notes:

- `ingest.py` reads only `MQTT_USERNAME` and `MQTT_PASSWORD`. It connects to `localhost:1883` and topic `greenhouse/telemetry`, both hard-coded; `MQTT_HOST`, `MQTT_PORT`, and `MQTT_TOPIC` are for the simulator.
- Every variable in `.env.example` is blank. A blank value is still "set", so `KAFKA_TOPIC=` makes the producer publish to topic `""`, and `KAFKA_BATCH_SIZE=` fails integer parsing. Fill in each value you keep or delete the line.
- `.env` is read when a process starts. After editing it, restart the service (`systemctl restart …`) or recreate containers (`sudo docker compose up -d`).
- The repository does not configure Mosquitto ACLs, so any authenticated MQTT user can publish and subscribe to any topic. Use a separate account per device and keep MQTT on trusted networks (port 1883 is not TLS).
- Restricting `.env` to the service user (`chmod 600 .env`) is sensible hygiene; nothing in the repo does it.

## Raspberry Pi gateway

Repository path used by the unit files: `/home/greenhousepi/greenhouse-iot-streaming-pipeline`, user and group `greenhousepi`.

### Initial setup

No provisioning script exists. The steps below are reconstructed from the repo's configuration and have not been run as a script.

```bash
git clone https://github.com/0GregoryJ/greenhouse-iot-streaming-pipeline.git
cd greenhouse-iot-streaming-pipeline

python3 -m venv .venv
.venv/bin/pip install -r requirements/gateway.txt

cp .env.example .env            # then fill in every value you keep

sudo cp infrastructure/mosquitto/greenhouse.conf /etc/mosquitto/conf.d/greenhouse.conf
sudo mosquitto_passwd -c /etc/mosquitto/passwd <mqtt-user>   # -c creates the file; omit it to add more users
sudo systemctl restart mosquitto
```

Then create the SQLite database by starting ingest (it creates `gateway/data/sensor_events.db` and the table) and apply the index migration (see below). Install the unit files after reading the warning in the next section.

### Installing systemd units

> **Check the ingest unit first.** [`infrastructure/systemd/greenhouse-ingest.service`](../infrastructure/systemd/greenhouse-ingest.service) in this repository is incomplete: its `ExecStart` ends at `.venv/bin/python>` with no script argument, and it has no `[Install]` section. Running the install script copies it over `/etc/systemd/system/greenhouse-ingest.service`. Compare with the deployed unit first (`systemctl cat greenhouse-ingest.service`) and fix the repo copy before installing. The intended form likely mirrors the producer unit (`python -u …/gateway/ingest.py` plus `WantedBy=multi-user.target`), but confirm against the working unit on the Pi.

```bash
sudo bash infrastructure/scripts/install-pi-services.sh
```

The script requires root and the `greenhousepi` user, runs `systemd-analyze verify` on the six units, installs them to `/etc/systemd/system/`, and runs `daemon-reload`. It does not enable or restart anything. Then:

```bash
sudo systemctl enable --now greenhouse-cleanup.timer
sudo systemctl enable --now greenhouse-health.timer
sudo systemctl enable --now greenhouse-kafka-producer.service   # has an [Install] section
# greenhouse-ingest.service: enable once its unit has an [Install] section
```

### Database migration

Ingest creates the `sensor_events` table (`CREATE TABLE IF NOT EXISTS`). The only migration, [`002_outbox_indexes.sql`](../gateway/migrations/002_outbox_indexes.sql), adds two partial indexes. There is no migration runner and no version table; apply by hand. The statements use `IF NOT EXISTS`, so re-running is safe:

```bash
sqlite3 gateway/data/sensor_events.db < gateway/migrations/002_outbox_indexes.sql
sqlite3 gateway/data/sensor_events.db ".indexes sensor_events"
```

The commit history says the migration was applied, but not on which hosts. A freshly created database does not have the indexes until you apply it, so confirm with `.indexes` on the Pi.

### Updating

```bash
cd ~/greenhouse-iot-streaming-pipeline
git pull --ff-only

# Only if requirements/gateway.txt changed
.venv/bin/pip install -r requirements/gateway.txt

# Restart only what changed
sudo systemctl restart greenhouse-ingest              # ingest.py or schemas/ changed
sudo systemctl restart greenhouse-kafka-producer      # kafka_producer.py or .env changed

# Only if infrastructure/systemd/ changed (see warning above)
sudo bash infrastructure/scripts/install-pi-services.sh

bash infrastructure/scripts/verify-deployment.sh pi
```

- Cleanup and health run as one-shot services from timers, so new code is picked up on the next run. Unit file changes need the install script.
- Restarting ingest briefly stops consumption; Mosquitto queues for the persistent session (limits not set in this repo). The producer unit allows `TimeoutStopSec=90` so in-flight deliveries can finish. See [Operations](operations.md#producer-backlog) for what a hard stop can duplicate.
- Mosquitto configuration changes: `sudo cp infrastructure/mosquitto/greenhouse.conf /etc/mosquitto/conf.d/greenhouse.conf && sudo systemctl restart mosquitto`. This disconnects the ESP32 and ingest, and both reconnect.

### Rollback

There are no release artifacts. Roll back by returning the working tree to a known commit and restarting:

```bash
git log --oneline -5
git checkout <previous-commit>      # detached HEAD; run `git checkout main` afterwards
sudo systemctl restart greenhouse-ingest greenhouse-kafka-producer
```

Prefer `git revert` on `main` and a normal pull when the bad change is merged. The SQLite database is not rolled back: rows written under the newer code stay, and the migration is not reversible by a script (to undo it, `DROP INDEX` both indexes). Rolling the gateway back below a schema version that devices already emit causes those events to be rejected and dropped.

## Kafka (EC2 #1)

Single-node KRaft broker, node ID 1, listener on a Tailscale address (port 9092), controller on `127.0.0.1:9093`, data in `/home/ubuntu/kafka-data`, 1 partition and replication factor 1 by default, 168 h retention. The template is [`greenhouse.properties.example`](../infrastructure/kafka/greenhouse.properties.example); the deployed file is `/home/ubuntu/kafka/config/greenhouse.properties`. Kafka installation, KRaft storage formatting, and the `kafka` systemd unit are **not documented or versioned in this repository** (**TBD**).

Topic: `greenhouse.sensor-readings`. No script creates it; `verify-deployment.sh kafka` only checks that it exists. The template does not disable auto-creation, so a producer's first write would create it with the default of one partition, but confirm this on your broker. An explicit create, if needed:

```bash
~/kafka/bin/kafka-topics.sh --bootstrap-server "$KAFKA_BOOTSTRAP_SERVERS" \
  --create --topic greenhouse.sensor-readings --partitions 1 --replication-factor 1
```

Update configuration:

```bash
nano /home/ubuntu/kafka/config/greenhouse.properties      # replace <TAILSCALE_IP> in the template copy
sudo systemctl restart kafka
sudo systemctl status kafka --no-pager
```

A restart interrupts producers and consumers. The Pi buffers in SQLite and the consumer reconnects, but expect brief backlog. With replication factor 1, broker storage loss is data loss. Verify from the repository root on EC2 #1:

```bash
export KAFKA_BOOTSTRAP_SERVERS=<TAILSCALE_IP>:9092
bash infrastructure/scripts/verify-deployment.sh kafka
```

## Serving host (EC2 #2)

Docker Compose runs `redis` (`redis:7-alpine`, AOF persistence, volume `redis_data`), `live-consumer`, and `api` (published only on `127.0.0.1:8000`). All three use `restart: unless-stopped`. Caddy runs on the host under systemd.

### Initial setup

Not scripted. Requirements from the configuration: Docker with Compose, Tailscale (the consumer must reach Kafka), Caddy, a DNS name for the API, and ports 80 and 443 open publicly.

```bash
git clone https://github.com/0GregoryJ/greenhouse-iot-streaming-pipeline.git
cd greenhouse-iot-streaming-pipeline
cp .env.example .env      # set KAFKA_BOOTSTRAP_SERVERS, KAFKA_TOPIC, KAFKA_CONSUMER_GROUP, CORS_ORIGINS
sudo docker compose config --quiet
sudo docker compose up -d --build
```

### Updating containers

```bash
cd <repository root>
git pull --ff-only
sudo docker compose config --quiet
sudo docker compose up -d --build
sudo docker compose ps
sudo bash infrastructure/scripts/verify-deployment.sh backend
```

Compose recreates only services whose image or configuration changed. Redis data survives (`redis_data` volume); `docker compose down -v` deletes it, so avoid `-v`. Logs: [Operations](operations.md#logs).

### Caddy

The template contains a placeholder hostname, so edit the deployed file rather than copying over it. Validate, then reload:

```bash
sudo nano /etc/caddy/Caddyfile        # reverse_proxy 127.0.0.1:8000, encode zstd gzip
sudo caddy validate --config /etc/caddy/Caddyfile
sudo systemctl reload caddy
curl --fail https://api.gregoryjoshua.com/health
```

### Rollback

Images are built on the host and not tagged or pushed to a registry. To roll back, check out the previous commit and rebuild:

```bash
git checkout <previous-commit>
sudo docker compose up -d --build
sudo docker compose ps
```

Return to `main` afterwards. Compose reuses cached layers where it can. Redis data is derived and can be rebuilt from Kafka (the procedure is untested; see [Operations](operations.md#4-kafka-has-events-but-redis-is-empty)). Changing the consumer group name replays retained events into Redis.

## Dashboard (Netlify)

The React/Vite app in [`dashboard/`](../dashboard/) is deployed from Git by Netlify to `https://greenhouse.gregoryjoshua.com`. **No `netlify.toml` or `_redirects` file exists in the repository**, so the Netlify build settings could not be confirmed here. From `dashboard/package.json` the expected settings are base directory `dashboard`, build command `npm run build`, publish directory `dashboard/dist`. Confirm them in the Netlify site settings.

The API URL is hard-coded in [`dashboard/src/App.jsx`](../dashboard/src/App.jsx); there is no environment configuration. The API must list the dashboard origin in `CORS_ORIGINS`, and `http://localhost:5173` (the default) allows local development against the production API.

```bash
cd dashboard
npm ci
npm run lint      # oxlint
npm run build     # vite build, output in dashboard/dist
npm run dev       # local dev server (Vite, port 5173 by default)
```

These scripts come from `package.json`; they were not run while writing this document. To deploy, push to the branch Netlify tracks and check the deploy log. To roll back, revert the commit, or use Netlify's published-deploy selector (a Netlify feature, not part of this repo).

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
- MicroPython runs `main.py` at boot. A boot-time exception (such as `Soil sensor not detected`) leaves the board at the REPL until reset.
- Verify: the REPL shows `Connected to MQTT` and `Published:` lines, then follow the checks in [Operations](operations.md#troubleshooting-flow).
- Rollback: check out the previous commit locally, copy the older files, and reset. The device has no firmware versioning or version reporting (**Planned**).

## Simulator

`sensor_simulator/simulate.py` publishes synthetic schema v1 events from a Mac to the Pi's Mosquitto (three per second, using `MQTT_*` from `.env`; dependencies in `requirements/simulator.txt`). **It currently fails at startup** with `FileNotFoundError`, because it loads `schemas/sensor_event.schema.json`, which was renamed to `sensor_event.v1.schema.json`. The fix is a one-line path change in the simulator and is not part of this documentation work.

## systemd units

| Unit | Host | Purpose |
| --- | --- | --- |
| `mosquitto.service` | Pi | MQTT broker |
| `greenhouse-ingest.service` | Pi | MQTT to SQLite (see the repo-unit warning above) |
| `greenhouse-kafka-producer.service` | Pi | SQLite to Kafka |
| `greenhouse-cleanup.service`, `greenhouse-cleanup.timer` | Pi | Hourly retention cleanup |
| `greenhouse-health.service`, `greenhouse-health.timer` | Pi | Health check every minute |
| `tailscaled.service` | Pi, both EC2 hosts | Private network (the producer unit orders after it; `verify-deployment.sh kafka` checks it) |
| `kafka.service` | EC2 #1 | Kafka broker (unit not in the repo) |
| `caddy.service` | EC2 #2 | HTTPS reverse proxy |

## Verification

[`verify-deployment.sh`](../infrastructure/scripts/verify-deployment.sh) is read-only and exits 1 on any failure:

| Argument | Checks |
| --- | --- |
| `pi` | `mosquitto`, `greenhouse-ingest`, `greenhouse-kafka-producer` active; cleanup and health timers enabled and active; `gateway/health.py` result (warning prints `WARN` but does not fail) |
| `kafka` | `kafka` and `tailscaled` active; `~/kafka/bin/kafka-topics.sh` present; topic listed (needs `KAFKA_BOOTSTRAP_SERVERS`) |
| `backend` | Compose config valid; `redis`, `live-consumer`, `api` containers running; `http://127.0.0.1:8000/health`; `https://api.gregoryjoshua.com/health` (hard-coded) |

It does not check data flow, Caddy, Redis contents, consumer lag, or the dashboard. After any deployment, also confirm fresh data end to end with the staged checks in [Operations](operations.md#troubleshooting-flow): new rows in SQLite, a rising Kafka offset, `Processed event=…` in the consumer log, and a "Live" dashboard.

## Coordinated changes and schema migrations

Use this order for changes that touch more than one component. Rule of thumb: **the validator must accept the new data before any device emits it, and readers must cope with it before it appears.**

| Change | Order |
| --- | --- |
| Firmware only, existing schema | Firmware |
| New sensor with an existing measurement type and unit | Firmware (dashboard polish optional) |
| New measurement type or unit (new schema version) | 1. Schema files, `ingest.py` `SCHEMAS`, tests, merge, CI green. 2. Pi: pull, restart `greenhouse-ingest`. 3. Test with a synthetic event ([steps](adding-a-sensor.md#test-the-gateway-with-a-synthetic-event)). 4. Serving host and dashboard, only if changed. 5. Firmware |
| New or removed field, changed key structure | As above, with consumer and API updated and verified **before** the firmware emits the new shape. Breaking changes need a new version and a transition period; see [Data contracts](data-contracts.md#compatibility-rules) |
| SQLite outbox change | Manual migration on the Pi. Stop ingest and producer while altering the table. Only index migrations exist today; other cases are **TBD** |
| Kafka topic or key change | Not documented (**TBD**). Plan consumers first, and remember a single-partition, RF 1 topic |

Do not remove support for an old schema version until no device emits it and queued or outbox events have drained. Kafka retains old-version events for up to 168 h by default.

## Rollback summary

| Component | Method | Caveat |
| --- | --- | --- |
| Pi services | Check out the previous commit, restart | Database contents and migrations are not reverted |
| Kafka config | Restore the previous properties file, restart | Single broker, no replication |
| Containers | Check out the previous commit, `docker compose up -d --build` | No image registry or tags |
| Dashboard | Revert and push, or select a prior Netlify deploy | Settings not in the repo |
| Firmware | Copy older files from Git, reset | No versioning on the device |
| Redis state | Rebuild from Kafka by changing the consumer group | Untested; limited to Kafka retention |

## Known limitations and repository discrepancies

Issues found while writing these documents. None were changed, because this task did not modify behavior.

1. **Truncated ingest unit.** `greenhouse-ingest.service` in the repo is incomplete (see above). Verify what is deployed on the Pi.
2. **File name casing.** `compose.yaml` references `consumers/live/Dockerfile` and `api/Dockerfile`, but the tracked files are `dockerfile` (lowercase). The infrastructure README refers to `caddy/Caddyfile`, but the file is `infrastructure/caddy/caddyfile`. macOS's case-insensitive filesystem hides this. How the live EC2 host builds could not be confirmed. On a case-sensitive Linux filesystem, a mismatch can break `docker compose build`. Renaming with `git mv` is a possible fix.
3. **Infrastructure README layout.** It lists `systemd/greenhouse-kafka.service`, which does not exist, and calls the scripts directory `scripts/` (actual: `infrastructure/scripts/`). It calls itself a "target layout".
4. **Unversioned Kafka host setup.** Kafka service unit, KRaft formatting, topic creation, and Tailscale setup are not in the repo.
5. **No migration runner.** Applied by hand; see above.
6. **`.env.example` blanks** break the producer if copied verbatim (see Configuration).
7. **Hard-coded dashboard API URL**, and Netlify settings not in the repo.
8. **Verification scope.** `verify-deployment.sh` covers service and container state, not data flow. Its public URL is hard-coded.
9. **Broken simulator** (see above).
10. **Security posture.** MQTT is authenticated but unencrypted and has no ACLs. Kafka uses `PLAINTEXT` and relies on Tailscale. Kafka is a single broker with no replication. ESP32 credentials are plaintext on the device.
11. **Manual provisioning.** EC2 instances, security groups, DNS, and Tailscale are configured by hand.
