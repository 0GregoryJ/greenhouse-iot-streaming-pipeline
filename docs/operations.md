# Operations

How to check, troubleshoot, and maintain the running pipeline.

Related documents: [Architecture](architecture.md) · [Data contracts](data-contracts.md) · [Deployment](deployment.md) · [Adding a sensor](adding-a-sensor.md)

## Conventions

| Host | Run commands from | Notes |
| --- | --- | --- |
| Raspberry Pi | `~/greenhouse-iot-streaming-pipeline` (units use `/home/greenhousepi/greenhouse-iot-streaming-pipeline`) | Python in `.venv/`. SQLite at `gateway/data/sensor_events.db` |
| Kafka EC2 (#1) | Any directory | Kafka CLI tools at `~/kafka/bin/` |
| Serving EC2 (#2) | The repository root (where `compose.yaml` and `.env` are) | Docker commands use `sudo` |
| Mac | Repository root, `.venv` activated | ESP32 serial access via `mpremote` |

Placeholders in angle brackets, such as `<TAILSCALE_IP>`, are values from your environment. Several commands load `.env` with `set -a; source .env; set +a`.

## Health at a glance

| Component | Check | Healthy |
| --- | --- | --- |
| ESP32 | `mpremote connect "$ESP32_PORT" repl` | `BME280 initialized`, `Soil sensor initialized`, then repeating `Published: <sensor> <type> <value> <unit>` lines |
| Mosquitto | `systemctl status mosquitto` and [`mosquitto_sub`](#mqtt) | Active; events stream |
| Ingest | `systemctl status greenhouse-ingest`, journal | Active; `Saved:` lines; no restarts |
| SQLite outbox | [Queries](#sqlite) | `latest_received` within seconds; `pending` near 0 |
| Producer | `systemctl status greenhouse-kafka-producer`, journal | `Batch complete: … acknowledged=N failed=0` |
| Gateway health | `.venv/bin/python gateway/health.py` | `"status": "healthy"`, exit code 0 |
| Kafka | `kafka-get-offsets.sh` run twice | End offset increases |
| Consumer | `sudo docker compose logs --tail 20 live-consumer` | `Processed event=… updated=True` |
| Redis | `redis-cli --scan` | One key per sensor/measurement |
| API | `curl -s http://127.0.0.1:8000/health` | `{"status":"ok"}` |
| Public API | `curl -s https://api.gregoryjoshua.com/health` | `{"status":"ok"}` |
| Dashboard | Browser | "Live" status pill, readings under 30 s old |

[`infrastructure/scripts/verify-deployment.sh`](../infrastructure/scripts/verify-deployment.sh) runs service, container, health-endpoint, and gateway-health checks per host (`pi`, `kafka`, `backend`). It is read-only and exits non-zero on failure. Data flow is checked with the [troubleshooting flow](#troubleshooting-flow). See [Deployment](deployment.md#verification).

## Logs

| Component | Command | Notes |
| --- | --- | --- |
| Ingest | `sudo journalctl -u greenhouse-ingest -f` | Written with `print()`; the unit runs Python unbuffered (`-u`) |
| Producer | `sudo journalctl -u greenhouse-kafka-producer -f` | Timestamped logging; the unit uses `python -u` |
| Cleanup | `sudo journalctl -u greenhouse-cleanup.service -n 20 --no-pager` | One run per hour |
| Health | `sudo journalctl -u greenhouse-health.service --since "3 minutes ago" -o cat` | JSON output once per minute |
| Mosquitto | `sudo journalctl -u mosquitto -n 50 --no-pager` | Or `/var/log/mosquitto/`, depending on the Pi's Mosquitto setup |
| Kafka | `sudo journalctl -u kafka -n 100 --no-pager` | On EC2 #1 |
| Consumer | `sudo docker compose logs -f live-consumer` | |
| API | `sudo docker compose logs -f api` | |
| Redis | `sudo docker compose logs redis` | |
| Caddy | `sudo journalctl -u caddy -n 50 --no-pager` | On EC2 #2 |

Messages worth knowing:

| Source | Message | Meaning |
| --- | --- | --- |
| ESP32 | `BME280 initialized`, `Soil sensor initialized` | Sensor ready (logged at boot and after each recovery) |
| ESP32 | `<sensor> initialization failed: <reason>` | Sensor not detected or init error; retried every 30 s while other sensors keep publishing |
| ESP32 | `BME280 read failed: …`, `Soil sensor read failed: …` | Read error; the sensor is marked unavailable and re-initialized within 30 s |
| ESP32 | `NTP synchronization failed: <reason>` | Clock sync failed; publishing continues if the clock was already set, otherwise the network retry path runs |
| ESP32 | `Telemetry error: <reason>` followed by `Network retry in 5 seconds` | Wi-Fi, NTP, or MQTT failure; reconnects without restarting the program |
| Ingest | `Subscribed to greenhouse/telemetry` | Connected |
| Ingest | `Saved: <type> = <value>` | Committed to SQLite and acknowledged |
| Ingest | `Duplicate ignored: <event_id>` | Redelivery or retry, already stored |
| Ingest | `Invalid event: <error>` | Rejected, acknowledged, dropped |
| Ingest | `Connection failed: <reason>` | MQTT credentials or broker problem |
| Ingest | `SQLite persistence failed` (traceback) | Process exits; systemd restarts it; message is redelivered |
| Producer | `Batch complete: fetched=… queued=… acknowledged=… failed=… enqueue_interrupted=…` | Per batch. Logged only when there are pending rows |
| Producer | `Kafka delivery failed event_id=…: <error>` | Row stays pending |
| Producer | `Incomplete batch; retrying in 5.0 seconds` | Retry after a failed or partial batch |
| Producer | `Producer queue full` | Local librdkafka queue is full; batch ends early |
| Consumer | `Processed event=… key=… updated=True/False` | `False` means Redis already held a newer timestamp |
| Consumer | `Skipping malformed event at partition=… offset=…: <error>` | Event skipped; offset committed |

## MQTT

Subscribe on the Pi. A second subscriber does not take messages from the ingestor (it uses its own client ID):

```bash
set -a; source .env; set +a
mosquitto_sub -h localhost -p 1883 -u "$MQTT_USERNAME" -P "$MQTT_PASSWORD" \
  -t greenhouse/telemetry -v
```

Capture ten messages and exit:

```bash
mosquitto_sub -h localhost -p 1883 -u "$MQTT_USERNAME" -P "$MQTT_PASSWORD" \
  -t greenhouse/telemetry -C 10
```

Count connected clients (expect at least the ESP32 and ingest, plus this command):

```bash
mosquitto_sub -h localhost -p 1883 -u "$MQTT_USERNAME" -P "$MQTT_PASSWORD" \
  -t '$SYS/broker/clients/connected' -C 1
```

To inject a labelled test event, see [Adding a sensor](adding-a-sensor.md#test-the-gateway-with-a-synthetic-event).

## SQLite

The table is `sensor_events(event_id, event_json, received_at, kafka_published_at)`. Event fields live inside `event_json`, so query them with `json_extract`. Open the database read-only and keep queries short:

```bash
DB=gateway/data/sensor_events.db

# Totals, backlog, and freshness
sqlite3 -readonly -header -column "$DB" \
  "SELECT COUNT(*) AS total,
          SUM(kafka_published_at IS NULL) AS pending,
          MAX(received_at) AS latest_received,
          MAX(kafka_published_at) AS latest_published
   FROM sensor_events;"

# Latest events
sqlite3 -readonly -header -column "$DB" \
  "SELECT received_at,
          json_extract(event_json, '$.sensor_id') AS sensor_id,
          json_extract(event_json, '$.measurement_type') AS measurement_type,
          json_extract(event_json, '$.value') AS value,
          json_extract(event_json, '$.unit') AS unit,
          kafka_published_at IS NOT NULL AS published
   FROM sensor_events ORDER BY received_at DESC LIMIT 12;"

# Ingest rate per minute
sqlite3 -readonly -header -column "$DB" \
  "SELECT substr(received_at, 1, 16) AS minute, COUNT(*) AS events
   FROM sensor_events GROUP BY 1 ORDER BY 1 DESC LIMIT 10;"

# Latest event per sensor and measurement
sqlite3 -readonly -header -column "$DB" \
  "SELECT json_extract(event_json, '$.sensor_id') AS sensor_id,
          json_extract(event_json, '$.measurement_type') AS measurement_type,
          MAX(received_at) AS latest
   FROM sensor_events GROUP BY 1, 2;"

# Pending (undelivered) rows by schema version
sqlite3 -readonly -header -column "$DB" \
  "SELECT json_extract(event_json, '$.schema_version') AS version, COUNT(*) AS pending
   FROM sensor_events WHERE kafka_published_at IS NULL GROUP BY 1;"
```

At the 5 s interval with four measurements, expect about 48 rows per minute. The database path is derived from the script location, so query the repository that the services run from. Pending rows are the only copy of an event until Kafka acknowledges it.

## Kafka

Run on the Kafka EC2 host. Set the bootstrap address (a Tailscale address) first:

```bash
export KAFKA_BOOTSTRAP_SERVERS=<TAILSCALE_IP>:9092
TOPIC=greenhouse.sensor-readings

# Does the topic exist? Partitions, replication
~/kafka/bin/kafka-topics.sh --bootstrap-server "$KAFKA_BOOTSTRAP_SERVERS" --describe --topic "$TOPIC"

# Topic-level overrides, such as retention (none means broker defaults apply)
~/kafka/bin/kafka-configs.sh --bootstrap-server "$KAFKA_BOOTSTRAP_SERVERS" \
  --describe --entity-type topics --entity-name "$TOPIC"

# End offset. Run twice, 30 seconds apart: it should increase
~/kafka/bin/kafka-get-offsets.sh --bootstrap-server "$KAFKA_BOOTSTRAP_SERVERS" --topic "$TOPIC"
```

Read the five most recent events (single partition, so partition 0; the end offset must be at least 5):

```bash
END=$(~/kafka/bin/kafka-get-offsets.sh --bootstrap-server "$KAFKA_BOOTSTRAP_SERVERS" --topic "$TOPIC" | cut -d: -f3)

~/kafka/bin/kafka-console-consumer.sh --bootstrap-server "$KAFKA_BOOTSTRAP_SERVERS" \
  --topic "$TOPIC" --partition 0 --offset $((END - 5)) \
  --max-messages 5 --timeout-ms 10000 --property print.key=true
```

Consumer lag for the live consumer. The default group is `greenhouse-live-dev`; confirm with `sudo docker compose exec live-consumer printenv KAFKA_CONSUMER_GROUP` on the serving host:

```bash
~/kafka/bin/kafka-consumer-groups.sh --bootstrap-server "$KAFKA_BOOTSTRAP_SERVERS" \
  --describe --group greenhouse-live-dev
```

Broker health: `sudo systemctl status kafka`, `df -h /home/ubuntu/kafka-data`, and `tailscale status`. The producer's own view is in its journal (`Batch complete: … acknowledged=…`).

## Redis and API

On the serving host:

```bash
sudo docker compose ps

# Keys and a single reading
sudo docker compose exec redis redis-cli --scan --pattern 'greenhouse:latest:*'
sudo docker compose exec redis redis-cli HGETALL greenhouse:latest:pi-001:bme280-001:air_temperature

# Persistence
sudo docker compose exec redis redis-cli INFO persistence | grep aof_enabled

# API
curl -s http://127.0.0.1:8000/health
curl -s http://127.0.0.1:8000/api/v1/sensors/latest | python3 -m json.tool
curl -s https://api.gregoryjoshua.com/health
```

Age of each reading as the API reports it (the dashboard calls anything over 30 s stale):

```bash
curl -s http://127.0.0.1:8000/api/v1/sensors/latest | python3 -c '
import json, sys
from datetime import datetime, timezone
now = datetime.now(timezone.utc)
for r in json.load(sys.stdin)["readings"]:
    ts = datetime.fromisoformat(r["timestamp"].replace("Z", "+00:00"))
    print(r["sensor_id"], r["measurement_type"], r["value"], r["unit"], f"{(now - ts).total_seconds():.0f}s old")
'
```

Each Redis hash holds `value`, `unit`, `timestamp`, `timestamp_ms`, `event_id`, `sensor_id`, `gateway_id`, `measurement_type`. `/health` returns 503 when Redis is unreachable, so it tests Redis, not data freshness.

## Gateway health monitoring

[`gateway/health.py`](../gateway/health.py) is read-only. `greenhouse-health.timer` runs it every minute through `greenhouse-health.service`, and the JSON goes to the journal. Run it by hand:

```bash
.venv/bin/python gateway/health.py; echo "exit=$?"
```

It reports `total_events`, `pending_events`, oldest pending age, latest received and delivered times and ages, database size, and disk usage. Defaults can be changed with flags such as `--ingest-stale-seconds`.

| Condition | Warning | Critical |
| --- | --- | --- |
| Latest stored event age | more than 120 s (also when no rows exist) | n/a |
| Oldest pending event age | more than 60 s | more than 300 s |
| Pending count | 1000 or more | 10 000 or more |
| Disk used | 80 % or more | 90 % or more |
| Pending rows but no Kafka delivery ever recorded | warning | n/a |
| Cannot open or read the database | n/a | critical |

Exit codes are 0 healthy, 1 warning, 2 critical. The service treats exit 1 as success, so warnings do not fail the unit, but a critical (exit 2) marks `greenhouse-health.service` failed. Check with `systemctl is-failed greenhouse-health.service`.

The check reads the Pi's outbox. A stale-ingestion warning covers both the ESP32 and ingest, so use stages 1 and 2 of the [troubleshooting flow](#troubleshooting-flow) to tell them apart. Downstream stages are checked with the commands in the Kafka and Redis sections.

## Cleanup and retention

| Data | Retention | Mechanism |
| --- | --- | --- |
| SQLite, acknowledged rows | 24 h after `kafka_published_at` | `greenhouse-cleanup.timer` (hourly, `Persistent=true`) runs `gateway/cleanup.py --retention-hours 24 --batch-size 1000` |
| SQLite, pending rows | Never deleted by age | Cleanup only touches rows with `kafka_published_at` set |
| Kafka | 168 h by the template's `log.retention.hours` | Broker setting; topic-level overrides: see the Kafka section |
| Redis | No expiry | Latest value per key; delete stale keys manually |

```bash
systemctl list-timers 'greenhouse-*' --no-pager       # next/last run
.venv/bin/python gateway/cleanup.py --dry-run          # counts eligible rows, deletes nothing
sudo systemctl start greenhouse-cleanup.service        # run once now
sudo journalctl -u greenhouse-cleanup.service -n 5 --no-pager   # "Cleanup completed; deleted=N retention_hours=24"
```

Deleted rows free pages inside the SQLite file for reuse, but nothing runs `VACUUM`, so the file does not shrink. Watch `disk_used_percent` in the health output if a long backlog forced it to grow.

## Troubleshooting flow

Follow the event from left to right and stop at the first stage where counts stop increasing.

```text
ESP32 prints "Published:"
  └─► MQTT shows events on greenhouse/telemetry          → stage 1
        └─► SQLite row count / latest_received grows     → stage 2
              └─► rows get kafka_published_at (pending≈0) → stage 3
                    └─► Kafka end offset grows            → stage 3
                          └─► Consumer logs "Processed"   → stage 4
                                └─► Redis keys refresh    → stage 4
                                      └─► API and dashboard fresh → stage 5
```

A quick triage from the Pi:

```bash
.venv/bin/python gateway/health.py        # backlog, freshness, disk in one view
systemctl status mosquitto greenhouse-ingest greenhouse-kafka-producer --no-pager
```

- `latest_received_age_seconds` large → stages 1 or 2.
- `pending_events` large or growing → stage 3.
- Both fine → stages 4 and 5 (serving host).

### 1. ESP32 publishes but MQTT shows nothing

A `Published:` line is printed only after the broker's PUBACK, so if the ESP32 prints it, Mosquitto has the message. Work out which side is wrong.

1. Read the device output (`mpremote connect "$ESP32_PORT" repl`). Healthy startup: `Wi-Fi connected`, `UTC synchronized`, `Connected to MQTT`, then `Published:` lines.
2. If it prints `Telemetry error: …` and `Network retry in 5 seconds`, that is the cause:

   | Output | Likely cause |
   | --- | --- |
   | `Wi-Fi connection timed out` | SSID or password, or not a 2.4 GHz network |
   | `Clock is not synchronized` or an NTP error | No internet for NTP |
   | `OSError` on connect | Wrong `MQTT_HOST` (must be the Pi's LAN address), broker down, or firewall |
   | `MQTTException: 5` | Credentials rejected |

3. If `Published:` lines appear but `mosquitto_sub` is silent, the subscriber is the problem: check the topic (`greenhouse/telemetry`), the credentials in `.env`, and that the ESP32's `MQTT_HOST` points at this Pi.
4. Check the broker: `systemctl status mosquitto`, the `$SYS` client count, and the broker log.

While disconnected, the ESP32 holds the current cycle's events in RAM and resumes sampling after it reconnects.

If some sensors are missing from the stream, check the REPL for `<sensor> initialization failed: …` (for example `BME280 not detected` or `Soil sensor not detected`) or `<sensor> read failed: …`. Check wiring and the I²C scan (see [Adding a sensor](adding-a-sensor.md#2-prove-the-sensor-on-the-bench)). The other sensors keep publishing, and the failed one is re-initialized every 30 s and logs `<sensor> initialized` when it recovers.

### 2. MQTT receives but SQLite is empty

```bash
systemctl status greenhouse-ingest --no-pager
systemctl show greenhouse-ingest -p ActiveState -p NRestarts
sudo journalctl -u greenhouse-ingest -n 100 --no-pager
```

| Observation | Cause and action |
| --- | --- |
| Service inactive or failed | It `Requires=mosquitto.service`. Start Mosquitto, then ingest. Read the journal for the first error |
| `Connection failed: …` | Wrong `MQTT_USERNAME`/`MQTT_PASSWORD` in `.env` |
| `Invalid event: …`, no `Saved:` | Validation failure, see [below](#schema-validation-failures) |
| Restarts climbing, `SQLite persistence failed` | Permissions on `gateway/data/`, full disk, or a corrupted database. Check `df -h` and file ownership |
| Rapid restarts with a Python traceback | Read the first traceback in the journal; the message that triggered it was not acknowledged |
| `Saved:` lines present but your query is empty | You queried a different repository clone or database path |
| Inactive for a while, now recovered | Mosquitto queued messages for the persistent session; rows appear after the restart |

### 3. SQLite has rows but Kafka is empty

```bash
sqlite3 -readonly -header -column gateway/data/sensor_events.db \
  "SELECT COUNT(*) AS pending, MIN(received_at) AS oldest_pending FROM sensor_events WHERE kafka_published_at IS NULL;"
sudo journalctl -u greenhouse-kafka-producer -n 100 --no-pager
```

| Observation | Cause and action |
| --- | --- |
| Producer inactive or crashed at start | A missing `KAFKA_BOOTSTRAP_SERVERS` in `.env` raises `KeyError` on import. Empty values in `.env` (such as `KAFKA_BATCH_SIZE=`) break integer parsing |
| `Kafka delivery failed … Local: Message timed out` | Broker unreachable for 60 s (`delivery.timeout.ms` default). Check `tailscale status` and the broker. The log line `Kafka servers: …` shows the configured address |
| `Incomplete batch; retrying …` repeating | Same as above; rows remain pending and are retried |
| Port test fails | `timeout 5 bash -c '</dev/tcp/<TAILSCALE_IP>/9092' && echo open` from the Pi |
| Connects but fails to produce | The broker's advertised address must be reachable from the Pi; check `advertised.listeners` on EC2 #1. Also confirm the topic exists (verify script lists it) |
| No log lines at all, pending is 0 | The producer logs only when rows exist. Check Kafka offsets instead |
| Pending is 0 but the consumer sees nothing | `KAFKA_TOPIC` differs between producer and consumer |

Confirm on the Kafka host with `kafka-get-offsets.sh` as shown above. Offsets that grow and `kafka_published_at` that fills in mean this stage is healthy.

### 4. Kafka has events but Redis is empty

On the serving host:

```bash
sudo docker compose ps
sudo docker compose logs --tail 100 live-consumer
```

| Observation | Cause and action |
| --- | --- |
| Container restarting | Compose `restart: unless-stopped` hides the crash. Read the logs. Redis unreachable at startup raises from `redis_client.ping()` |
| No `Processed` lines and lag grows | Consumer cannot reach Kafka. Test from the container: `sudo docker compose exec live-consumer python -c "import socket; socket.create_connection(('<TAILSCALE_IP>', 9092), 5); print('open')"` |
| `Processed … updated=False` | Redis already holds a newer timestamp for that key. See [Stale dashboard readings](#stale-dashboard-readings) |
| `Skipping malformed event …` | The event lacked a required field or had a bad timestamp or value. It was skipped permanently |
| Consumer healthy but Redis empty | Redis volume was lost, or the consumer group has no committed offset and no new events. See Redis recovery below |

Check lag with `kafka-consumer-groups.sh` (above). Lag near 0 and rising offsets mean the consumer is keeping up.

**Redis recovery.** Redis is a derived view. Start a consumer with a new `KAFKA_CONSUMER_GROUP` (set in `.env`, then `sudo docker compose up -d`); `auto.offset.reset=earliest` replays the retained 168 h. Alternatively, reset the group's offsets with `kafka-consumer-groups.sh --reset-offsets`.

### 5. Redis has data but the API or dashboard is empty or stale

```bash
curl -s http://127.0.0.1:8000/health
curl -s http://127.0.0.1:8000/api/v1/sensors/latest | python3 -m json.tool
curl -s https://api.gregoryjoshua.com/health
```

| Observation | Cause and action |
| --- | --- |
| Local `/health` returns 503 | API cannot reach Redis. Check `sudo docker compose ps redis` and its logs |
| Local works, public fails | Caddy or DNS: `sudo systemctl status caddy`, `sudo caddy validate --config /etc/caddy/Caddyfile`, and the Caddy journal |
| API works, dashboard shows "Offline" | Browser dev tools. A CORS error means the dashboard origin is missing from `CORS_ORIGINS` (set in `.env`, then `sudo docker compose up -d` to recreate the API container) |
| Dashboard shows "No data" | `/api/v1/sensors/latest` returns `count: 0`: Redis empty, go back to stage 4 |
| Dashboard shows "Stale" or grey cards | See [Stale dashboard readings](#stale-dashboard-readings) |

The dashboard keeps the last known values when a fetch fails, so check the status pill and reading ages, not only the numbers.

## Failure scenarios

### Schema validation failures

Symptoms: MQTT shows events, SQLite stops growing, ingest logs `Invalid event: …`.

```bash
sudo journalctl -u greenhouse-ingest --since "1 hour ago" --no-pager | grep "Invalid event"
```

| Error text | Meaning |
| --- | --- |
| `Unsupported schema version: N` | The Pi does not know version N. Pull the commit that adds it to `gateway/ingest.py` and `schemas/`, and restart ingest |
| `'x' is not one of [...]` | `measurement_type` or `unit` not in the enum for that version |
| `'hpa' was expected` | `atmospheric_pressure` sent with a different unit |
| `Additional properties are not allowed (...)` | Unknown field |
| `'<field>' is a required property` | Missing field |
| `... is not of type 'number'` | `value` is a string or boolean |
| `Expecting value` and similar | Payload is not JSON |

The journal records the error, not the payload. Capture an offending message with `mosquitto_sub -C` ([MQTT](#mqtt)) and validate it as in [Data contracts](data-contracts.md#testing-a-schema-change-before-deployment). The usual cause is a firmware change deployed before the gateway ([Deployment](deployment.md#coordinated-changes-and-schema-migrations)). Rejected events are acknowledged and logged, not stored.

### Network outages

| Outage | Effect | Check and recovery |
| --- | --- | --- |
| ESP32 loses Wi-Fi or the Pi | Sampling pauses; the current cycle is held in RAM | Automatic reconnect every 5 s; held events publish first |
| Pi loses internet or Tailscale | `pending_events` grows; ingestion continues | `tailscale status`. The producer retries every 5 s and drains oldest-first after recovery. The health check warns after 60 s of backlog age |
| Kafka host down | Same as above | `sudo systemctl status kafka` on EC2 #1 |
| Serving host cannot reach Kafka | Consumer lag grows; the dashboard goes stale | Kafka retains events (168 h). The consumer resumes from its committed offset |
| Public HTTPS fails | Dashboard shows "Offline" with last-known values | Caddy, DNS, certificates |

After a long outage the dashboard steps through old readings and marks them stale until the backlog is drained, then converges on the newest values.

### Producer backlog

```bash
.venv/bin/python gateway/health.py | head -30
df -h gateway/data
```

1. Find out why Kafka is not acknowledging ([stage 3](#3-sqlite-has-rows-but-kafka-is-empty)).
2. While it is down the database grows. Pending rows are not deleted by cleanup, so disk usage can reach the 80 % and 90 % health thresholds.
3. After recovery, watch `pending` fall. Each batch (100 rows by default, `KAFKA_BATCH_SIZE`) waits for all delivery results before the next starts. If the backlog does not shrink, read the `Batch complete` lines for `failed=`.
4. Restart safely with `sudo systemctl restart greenhouse-kafka-producer`. The unit allows 90 s for in-flight deliveries. After a hard stop, rows whose delivery succeeded but were not yet marked will be sent again, so duplicates in Kafka are possible.

### Consumer failures

| Failure | Behavior | Action |
| --- | --- | --- |
| Redis unavailable | The write raises; the consumer exits; Docker restarts it; the offset was not committed, so the event is retried | Fix Redis. Check `docker compose ps` and logs |
| Kafka unreachable | Lag grows; no log lines | Check connectivity as in stage 4 |
| Malformed event | Logged and skipped; offset committed | Find the source event; see [Data contracts](data-contracts.md#how-invalid-events-are-handled) |
| Crash loop | `RestartCount` rises: `sudo docker inspect -f '{{.RestartCount}}' $(sudo docker compose ps -q live-consumer)` | Read `docker compose logs live-consumer` for the traceback |
| Missing `KAFKA_BOOTSTRAP_SERVERS` | `docker compose` refuses to start (`Kafka address required`) | Set it in `.env` |

### Stale dashboard readings

A card is stale when its event `timestamp` is more than 30 s old. The dashboard colors by event age, not by when it last polled. Use the API's reading ages (script above) to find the stage:

| Pattern | Likely cause |
| --- | --- |
| All readings old, and `latest_received` on the Pi is also old | Upstream of SQLite: ESP32 or ingest (stages 1 and 2) |
| `latest_received` fresh, `pending` growing | Producer or Kafka (stage 3) |
| Kafka offsets rising, consumer lag growing | Consumer (stage 4) |
| Consumer logs `updated=False` for fresh events | Redis holds a **future** timestamp for that key. The Lua script rejects anything older. Check the device clock. A stored `timestamp_ms` ahead of real time blocks updates until time catches up, or until you `DEL` the key |
| Only one sensor's cards are stale | That sensor or its wiring. Check the ESP32 REPL for `read failed` or `initialization failed`; it is retried every 30 s |
| A retired sensor's card persists as stale | Redis keys never expire. `redis-cli DEL <key>` |
| API fresh, dashboard still stale | Browser cache or an old Netlify deploy |
| Extra cards with `sim-` IDs | The [simulator](deployment.md#simulator) ran. Its Redis keys (`greenhouse:latest:sim-gateway-001:*`) stay until deleted |
