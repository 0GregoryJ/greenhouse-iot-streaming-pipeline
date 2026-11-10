# ADR 0013: Snowflake history API with JWT key-pair auth

**Status:** Accepted
**Recorded:** 2026-11-09

## Context

The S3 historical archive ([ADR 0012](0012-historical-archive-to-s3.md)) retains every event, and dbt models in [`warehouse/`](../../warehouse/) turn the Snowflake raw table into hourly and daily marts. The live dashboard path still needs only Redis, but clients also need time-series history without querying S3 or Kafka directly. The API already runs on the serving host behind Caddy; adding a second data source there keeps one public HTTPS surface.

Snowflake access from the container must not embed long-lived passwords in the image. The serving host already holds an RSA private key for the API Snowflake user.

## Decision

- Expose `GET /api/v1/history/series` from FastAPI ([`api/routes/history.py`](../../api/routes/history.py)), with `sensor_id`, `measurement_type`, and `period` in {`24h`, `7d`, `30d`}.
- Query allow-listed mart tables only (`FCT_SENSOR_HOURLY` / `FCT_SENSOR_DAILY`) via [`api/repositories/snowflake.py`](../../api/repositories/snowflake.py). Table names and time windows are chosen in code, not from request text.
- Authenticate with `authenticator=SNOWFLAKE_JWT`, reading the PEM from `SNOWFLAKE_PRIVATE_KEY_PATH` and the passphrase from the environment.
- Compose mounts the host file `SNOWFLAKE_KEY_HOST_PATH` read-only at `/run/secrets/snowflake_api_key.pem` and sets `SNOWFLAKE_PRIVATE_KEY_PATH` to that path.
- Open Snowflake connections on demand. `/health` continues to check Redis only so a warehouse outage does not take down the live path.
- Keep dbt execution and the S3 → Snowflake load outside the API containers; the API assumes marts already exist.

## Consequences

- History is available over the same API and Caddy entry point as live readings.
- Live monitoring stays up when Snowflake is unreachable; history returns HTTP 503.
- The PEM must exist on the host before `docker compose up` and be readable by the container user (`appuser`).
- Schema drift between dbt marts and the repository SQL breaks history until both are updated together.
- Dashboard charts can call the endpoint without further backend work; wiring those charts remains a frontend task.
- CI history tests mock the service layer and do not need Snowflake credentials.

## Related

[Architecture](../architecture.md#event-flow), [Deployment](../deployment.md#serving-host-ec2-2), [Operations: Historical API and Snowflake](../operations.md#historical-api-and-snowflake), [ADR 0012](0012-historical-archive-to-s3.md)
