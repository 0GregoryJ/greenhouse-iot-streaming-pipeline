import { ageMs, formatAge, formatValue, isStale } from "../../lib/format.js";
import { metricInfo } from "../../lib/metrics.js";

export function ReadingCard({ reading, now }) {
  const { label } = metricInfo(reading.measurement_type);
  const { number, suffix } = formatValue(reading);
  const stale = isStale(reading.timestamp, now);
  const age = formatAge(ageMs(reading.timestamp, now));

  const showMeter = reading.unit === "percent";
  const meterWidth = Math.min(100, Math.max(0, Number(reading.value) || 0));

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

export function SkeletonCards() {
  return Array.from({ length: 3 }, (_, index) => (
    <div className="card skeleton" key={index} aria-hidden="true" />
  ));
}
