import { formatAge } from "../../lib/format.js";
import { metricInfo } from "../../lib/metrics.js";
import { ReadingCard, SkeletonCards } from "./ReadingCard.jsx";

function getStatus({ loaded, error, readings, now }) {
  if (error && readings.length === 0) return { key: "offline", label: "Offline" };
  if (!loaded) return { key: "connecting", label: "Connecting" };
  if (readings.length === 0) return { key: "empty", label: "No data" };

  const anyFresh = readings.some((reading) => {
    const eventTime = new Date(reading.timestamp).getTime();
    return Number.isFinite(eventTime) && now - eventTime <= 30_000;
  });

  return anyFresh
    ? { key: "live", label: "Live" }
    : { key: "stale", label: "Stale" };
}

export function LiveView({ readings, status: loadStatus, error, lastFetchedAt, now }) {
  const loaded = loadStatus !== "loading" || readings.length > 0;
  const sorted = [...readings].sort(
    (a, b) =>
      metricInfo(a.measurement_type).order -
        metricInfo(b.measurement_type).order ||
      String(a.sensor_id).localeCompare(String(b.sensor_id))
  );
  const status = getStatus({ loaded, error, readings, now });

  return (
    <section className="view" aria-label="Live sensor readings">
      <div className="view-toolbar">
        <div>
          <h2 className="view-title">Live monitoring</h2>
          <p className="view-copy">
            Current greenhouse readings from Redis, refreshed every few seconds.
          </p>
        </div>
        <div className="top-status">
          <span className={`pill pill-${status.key}`}>
            <span className="pill-dot" />
            {status.label}
          </span>
          {lastFetchedAt && (
            <span className="updated">
              Updated {formatAge(now - lastFetchedAt)}
            </span>
          )}
        </div>
      </div>

      {error && (
        <p className="notice" role="alert">
          {readings.length > 0
            ? "Can't reach the API. Showing the last known readings."
            : "Can't reach the API."}
        </p>
      )}

      <div className="grid">
        {!loaded && !error && <SkeletonCards />}

        {sorted.map((reading) => (
          <ReadingCard
            key={`${reading.gateway_id}-${reading.sensor_id}-${reading.measurement_type}`}
            reading={reading}
            now={now}
          />
        ))}
      </div>

      {loaded && !error && readings.length === 0 && (
        <p className="empty">No readings available yet.</p>
      )}

      <p className="page-foot">Live view refreshes every 3 seconds</p>
    </section>
  );
}
