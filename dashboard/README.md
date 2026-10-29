# Dashboard

React and Vite single-page app that shows the latest greenhouse sensor readings. It is the last stage of the [Greenhouse IoT Streaming Pipeline](../README.md); the data comes from the FastAPI service described in [Architecture](../docs/architecture.md).

Live site: <https://greenhouse.gregoryjoshua.com>

## Behavior

- Polls `GET /api/v1/sensors/latest` every 3 seconds (`POLL_INTERVAL_MS` in [`src/App.jsx`](src/App.jsx)).
- Renders one card per sensor and measurement type, labeled and ordered by the `METRICS` map. Unknown measurement types fall back to a generic label.
- Marks a reading stale when its event timestamp is more than 30 seconds old (`STALE_AFTER_MS`).
- Shows a status pill: **Connecting**, **Live** (at least one fresh reading), **Stale** (all readings stale), **No data**, or **Offline**. When a fetch fails, the last known readings stay on screen.
- Formats values by unit (`celsius`, `percent`, `hpa`, `raw_capacitance`); a `percent` reading also shows a 0 to 100 bar.

The API URL is the `API_URL` constant in `src/App.jsx`. The API allows the dashboard origin through its `CORS_ORIGINS` setting (`http://localhost:5173` by default, for local development).

## Commands

Run from this directory. Requires Node.js 22 (the version CI uses).

```bash
npm ci            # install dependencies
npm run dev       # dev server on http://localhost:5173
npm run lint      # oxlint
npm run build     # production build in dist/
npm run preview   # serve the production build locally
```

## Adding a measurement type

Add an entry to `METRICS` in `src/App.jsx` for a label and sort order, and a case in `formatValue` if the unit needs special formatting. See [Adding a sensor](../docs/adding-a-sensor.md#6-check-downstream-compatibility).

## CI and deployment

The `dashboard` job in [`.github/workflows/ci-cd.yml`](../.github/workflows/ci-cd.yml) runs `npm ci`, `npm run lint`, and `npm run build` on every push and pull request. Netlify builds and publishes the site from Git; see [Deployment](../docs/deployment.md#dashboard-netlify).
