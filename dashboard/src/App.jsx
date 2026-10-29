import { useEffect, useState } from "react";
import "./App.css";

const API_URL =
  "https://api.gregoryjoshua.com/api/v1/sensors/latest";

const POLL_INTERVAL_MS = 3000;
const STALE_AFTER_MS = 30_000;

// Display order and labels for known measurement types.
const METRICS = {
  air_temperature: { label: "Air temperature", order: 0 },
  relative_humidity: { label: "Relative humidity", order: 1 },
  atmospheric_pressure: { label: "Atmospheric pressure", order: 2 },
  soil_moisture: { label: "Soil moisture", order: 3 },
  soil_temperature: { label: "Soil temperature", order: 4 },
};

function metricInfo(type) {
  if (METRICS[type]) return METRICS[type];

  const label = String(type ?? "Unknown").replace(/_/g, " ");

  return {
    label: label.charAt(0).toUpperCase() + label.slice(1),
    order: Number.MAX_SAFE_INTEGER,
  };
}

function formatValue({ value, unit }) {
  switch (unit) {
    case "celsius":
      return { number: value.toFixed(1), suffix: "°C" };
    case "percent":
      return { number: value.toFixed(1), suffix: "%" };
    case "hpa":
      return { number: value.toFixed(1), suffix: "hPa" };
    case "raw_capacitance":
      return { number: Math.round(value).toString(), suffix: "raw" };
    default:
      return { number: String(value), suffix: unit ?? "" };
  }
}

function ageMs(timestamp, now) {
  const eventTime = new Date(timestamp).getTime();

  if (!Number.isFinite(eventTime)) return null;

  return Math.max(0, now - eventTime);
}

function isStale(timestamp, now) {
  const age = ageMs(timestamp, now);

  return age === null || age > STALE_AFTER_MS;
}

function formatAge(age) {
  if (age === null) return "unknown";

  const seconds = Math.floor(age / 1000);

  if (seconds < 5) return "just now";
  if (seconds < 60) return `${seconds}s ago`;

  const minutes = Math.floor(seconds / 60);

  if (minutes < 60) return `${minutes}m ago`;

  return `${Math.floor(minutes / 60)}h ago`;
}

function getStatus({ loaded, error, readings, now }) {
  if (error) return { key: "offline", label: "Offline" };
  if (!loaded) return { key: "connecting", label: "Connecting" };
  if (readings.length === 0) return { key: "empty", label: "No data" };

  const anyFresh = readings.some(
    (reading) => !isStale(reading.timestamp, now)
  );

  return anyFresh
    ? { key: "live", label: "Live" }
    : { key: "stale", label: "Stale" };
}

function ReadingCard({ reading, now }) {
  const { label } = metricInfo(reading.measurement_type);
  const { number, suffix } = formatValue(reading);
  const stale = isStale(reading.timestamp, now);
  const age = formatAge(ageMs(reading.timestamp, now));

  const showMeter = reading.unit === "percent";
  const meterWidth = Math.min(100, Math.max(0, reading.value));

  return (
    <article className={stale ? "card is-stale" : "card"}>
      <header className="card-head">
        <h2>{label}</h2>
        <span
          className={stale ? "dot dot-stale" : "dot dot-live"}
          title={stale ? "No recent update" : "Receiving updates"}
        />
      </header>

      <p className="value">
        <span className="number">{number}</span>
        <span className="suffix">{suffix}</span>
      </p>

      {showMeter && (
        <div
          className="meter"
          role="img"
          aria-label={`${label} ${number}${suffix}`}
        >
          <span style={{ width: `${meterWidth}%` }} />
        </div>
      )}

      <footer className="card-foot">
        <span className="sensor">{reading.sensor_id}</span>
        <time dateTime={reading.timestamp}>{age}</time>
      </footer>
    </article>
  );
}

function SkeletonCards() {
  return Array.from({ length: 3 }, (_, index) => (
    <div className="card skeleton" key={index} aria-hidden="true" />
  ));
}

function App() {
  const [readings, setReadings] = useState([]);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState(null);
  const [lastUpdated, setLastUpdated] = useState(null);
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const controller = new AbortController();

    async function fetchReadings() {
      try {
        const response = await fetch(API_URL, {
          signal: controller.signal,
        });

        if (!response.ok) {
          throw new Error(`API returned ${response.status}`);
        }

        const data = await response.json();

        setReadings(data.readings);
        setLastUpdated(Date.now());
        setError(null);
      } catch (err) {
        if (err.name === "AbortError") return;

        setError(err.message);
      } finally {
        if (!controller.signal.aborted) setLoaded(true);
      }
    }

    // Fetch immediately, then poll.
    fetchReadings();
    const poll = setInterval(fetchReadings, POLL_INTERVAL_MS);

    // Tick once a second so "updated Ns ago" labels stay current.
    const tick = setInterval(() => setNow(Date.now()), 1000);

    return () => {
      controller.abort();
      clearInterval(poll);
      clearInterval(tick);
    };
  }, []);

  const sorted = [...readings].sort(
    (a, b) =>
      metricInfo(a.measurement_type).order -
        metricInfo(b.measurement_type).order ||
      String(a.sensor_id).localeCompare(String(b.sensor_id))
  );

  const status = getStatus({ loaded, error, readings, now });

  return (
    <div className="page">
      <header className="top">
        <div>
          <h1>Greenhouse</h1>
          <p className="subtitle">Live sensor readings</p>
        </div>

        <div className="top-status">
          <span className={`pill pill-${status.key}`}>
            <span className="pill-dot" />
            {status.label}
          </span>
          {lastUpdated && (
            <span className="updated">
              Updated {formatAge(now - lastUpdated)}
            </span>
          )}
        </div>
      </header>

      {error && (
        <p className="notice" role="alert">
          {readings.length > 0
            ? "Can't reach the API. Showing the last known readings."
            : "Can't reach the API."}
        </p>
      )}

      <main className="grid">
        {!loaded && !error && <SkeletonCards />}

        {sorted.map((reading) => (
          <ReadingCard
            key={`${reading.gateway_id}-${reading.sensor_id}-${reading.measurement_type}`}
            reading={reading}
            now={now}
          />
        ))}
      </main>

      {loaded && !error && readings.length === 0 && (
        <p className="empty">No readings available yet.</p>
      )}

      <footer className="page-foot">Refreshes every 3 seconds</footer>
    </div>
  );
}

export default App;
