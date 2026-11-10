# Dashboard

React and Vite single-page app for greenhouse monitoring. It is the last stage of the [Greenhouse IoT Streaming Pipeline](../README.md); data comes from the FastAPI service described in [Architecture](../docs/architecture.md).

Live site: <https://greenhouse.gregoryjoshua.com>

## Behavior

Two tabs share the same design language:

### Live

- Polls `GET /api/v1/sensors/latest` every 3 seconds (`useLiveReadings`).
- Renders one card per sensor and measurement type, labeled and ordered by the `METRICS` map in [`src/lib/metrics.js`](src/lib/metrics.js). Unknown measurement types fall back to a generic label.
- Marks a reading stale when its event timestamp is more than 30 seconds old (`STALE_AFTER_MS` in [`src/lib/format.js`](src/lib/format.js)).
- Shows a status pill: **Connecting**, **Live** (at least one fresh reading), **Stale** (all readings stale), **No data**, or **Offline**. When a fetch fails, the last known readings stay on screen.
- Formats values by unit (`celsius`, `percent`, `hpa`, `raw_capacitance`); a `percent` reading also shows a 0 to 100 bar.

### History

- Calls `GET /api/v1/history/series` with `sensor_id`, `measurement_type`, and `period` (`24h`, `7d`, or `30d`).
- Discovers selectable sensors and measurement types from the live latest payload (warehouse-only sensors are not listed until a history metadata endpoint exists).
- Charts average over time with a min–max band (Recharts). Missing intervals stay as gaps, not zeros.
- Shows weighted period summaries (`sum(avg × count) / sum(count)`), extrema, total readings, and light start→end insights derived only from the returned points.
- Distinguishes warehouse aggregates from the current live reading for the same series.
- Handles loading, empty, HTTP error, and unavailable-API states without mock data.

The History chunk is lazy-loaded so the Live tab stays smaller.

## Configuration

API origin comes from [`src/api/config.js`](src/api/config.js):

- Build-time override: `VITE_API_URL` or `VITE_API_BASE_URL` (origin only, or a `…/api/v1` base; trailing slash optional).
- Default: `https://api.gregoryjoshua.com`.

The API allows the dashboard origin through its `CORS_ORIGINS` setting (`http://localhost:5173` by default, for local development).

## Layout

```text
src/
├── api/config.js
├── components/
│   ├── live/          LiveView, ReadingCard
│   └── history/       HistoryView, Chart, Controls, Summary, Insights
├── hooks/             useLiveReadings, useHistoricalSeries
├── lib/               metrics, format, historyStats (+ tests)
├── services/          liveApi, historyApi
└── App.jsx            Live | History tabs
```

## Commands

Run from this directory. Requires Node.js 22 (the version CI uses).

```bash
npm ci            # install dependencies
npm run dev       # dev server on http://localhost:5173
npm run lint      # oxlint
npm run test      # node:test for history summary / timeline helpers
npm run build     # production build in dist/
npm run preview   # serve the production build locally
```

## Adding a measurement type

Add an entry to `METRICS` in [`src/lib/metrics.js`](src/lib/metrics.js) for a label and sort order, and a case in `formatValue` in [`src/lib/format.js`](src/lib/format.js) if the unit needs special formatting. See [Adding a sensor](../docs/adding-a-sensor.md#6-check-downstream-compatibility).

## CI and deployment

The `dashboard` job in [`.github/workflows/ci-cd.yml`](../.github/workflows/ci-cd.yml) runs `npm ci`, `npm run lint`, `npm run test`, and `npm run build` on every push and pull request. Netlify builds and publishes the site from Git; see [Deployment](../docs/deployment.md#dashboard-netlify).
