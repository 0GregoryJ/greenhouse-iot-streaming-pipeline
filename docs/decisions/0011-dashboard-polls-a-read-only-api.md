# ADR 0011: Dashboard polls a read-only API

**Status:** Accepted
**Recorded:** 2026-10-28

## Context

The dashboard shows the latest reading per sensor. Readings arrive every few seconds, and a short delay is acceptable. The dashboard is a static site on Netlify, and the data lives behind the serving host. The simplest design that works with static hosting, standard HTTPS, and a CDN-hosted front end is preferred.

## Decision

The React/Vite dashboard **Live** tab polls `GET /api/v1/sensors/latest` every 3 seconds. FastAPI is read-only for that path: it scans the `greenhouse:latest:*` keys in Redis and returns a sorted list. `GET /health` pings Redis. Caddy provides HTTPS in front of FastAPI, and a CORS allow-list on the API permits the dashboard origin.

The dashboard decides staleness itself: a reading is stale when its event timestamp is older than 30 seconds. When a fetch fails, it keeps the last known readings and shows an "Offline" status.

Historical analytics use a separate read-only path: `GET /api/v1/history/series` against Snowflake marts ([ADR 0013](0013-snowflake-history-api-with-jwt-key.md)). The History tab still discovers selectable sensors from the live endpoint.

## Consequences

- No long-lived connections, WebSocket server, or fan-out state to operate; the live API is stateless.
- Worst-case live latency is the poll interval plus the pipeline's own delay.
- Load grows with the number of open dashboards, which suits a small audience.
- Staleness is computed from event time, so a stopped sensor is visible even when the API is healthy.
- `/health` tests Redis only. Data freshness is judged by reading ages, not by that endpoint.
- The API origin is build-time configurable via `VITE_API_URL` / `VITE_API_BASE_URL` ([`dashboard/src/api/config.js`](../../dashboard/src/api/config.js)), with a production default.
- History charts share the same HTTPS API surface but do not depend on Redis; a Snowflake outage leaves Live working.

## Related

[Architecture](../architecture.md#event-flow), [`api/main.py`](../../api/main.py), [`dashboard/`](../../dashboard/), [`tests/api/test_api.py`](../../tests/api/test_api.py), [ADR 0013](0013-snowflake-history-api-with-jwt-key.md)
