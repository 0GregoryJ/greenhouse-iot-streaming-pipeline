# ADR 0011: Dashboard polls a read-only API

**Status:** Accepted
**Recorded:** 2026-10-28

## Context

The dashboard shows the latest reading per sensor. Readings arrive every few seconds, and a short delay is acceptable. The dashboard is a static site on Netlify, and the data lives behind the serving host. The simplest design that works with static hosting, standard HTTPS, and a CDN-hosted front end is preferred.

## Decision

The React/Vite dashboard polls `GET /api/v1/sensors/latest` every 3 seconds. FastAPI is read-only: it scans the `greenhouse:latest:*` keys in Redis and returns a sorted list. `GET /health` pings Redis. Caddy provides HTTPS in front of FastAPI, and a CORS allow-list on the API permits the dashboard origin.

The dashboard decides staleness itself: a reading is stale when its event timestamp is older than 30 seconds. When a fetch fails, it keeps the last known readings and shows an "Offline" status.

## Consequences

- No long-lived connections, WebSocket server, or fan-out state to operate; the API is stateless.
- Worst-case latency is the poll interval plus the pipeline's own delay.
- Load grows with the number of open dashboards, which suits a small audience.
- Staleness is computed from event time, so a stopped sensor is visible even when the API is healthy.
- `/health` tests Redis only. Data freshness is judged by reading ages, not by that endpoint.
- The API URL is set in `App.jsx`. Moving it to build-time configuration is on the [roadmap](../../README.md#roadmap).
- Historical views need a different data path (the planned warehouse), not this API.

## Related

[Architecture](../architecture.md#event-flow), [`api/main.py`](../../api/main.py), [`dashboard/src/App.jsx`](../../dashboard/src/App.jsx), [`tests/api/test_api.py`](../../tests/api/test_api.py)
