import { formatAge, formatChartTooltipTime, formatValue, PERIOD_LABELS } from "../../lib/format.js";

export function HistorySummary({
  summary,
  period,
  resolution,
  unit,
  liveReading,
  now,
}) {
  const cards = [
    {
      key: "avg",
      label: "Period average",
      hint: "Weighted by reading count",
      value: summary.weightedAvg,
    },
    {
      key: "min",
      label: "Lowest recorded",
      hint: "Min across intervals",
      value: summary.min,
    },
    {
      key: "max",
      label: "Highest recorded",
      hint: "Max across intervals",
      value: summary.max,
    },
    {
      key: "count",
      label: "Total readings",
      hint: `${summary.intervalCount} aggregated ${resolution === "day" ? "days" : "hours"}`,
      value: summary.totalReadings,
      raw: true,
    },
  ];

  const latestLabel = summary.latestTimestamp
    ? formatChartTooltipTime(summary.latestTimestamp, resolution)
    : null;
  const latestAge = summary.latestTimestamp
    ? formatAge(Math.max(0, now - new Date(summary.latestTimestamp).getTime()))
    : null;

  return (
    <div className="history-summary">
      <div className="summary-grid">
        {cards.map((card) => {
          const formatted = card.raw
            ? {
                number: Number(card.value ?? 0).toLocaleString(),
                suffix: "",
              }
            : formatValue({ value: card.value, unit });

          return (
            <article className="summary-card" key={card.key}>
              <h3>{card.label}</h3>
              <p className="value">
                <span className="number summary-number">{formatted.number}</span>
                {formatted.suffix && (
                  <span className="suffix">{formatted.suffix}</span>
                )}
              </p>
              <p className="summary-hint">{card.hint}</p>
            </article>
          );
        })}
      </div>

      <div className="summary-meta">
        <p>
          Showing {PERIOD_LABELS[period] ?? period} aggregates
          {resolution === "day" ? " (daily)" : " (hourly)"}. Historical values
          are warehouse marts and may lag behind live readings.
        </p>
        {latestLabel && (
          <p>
            Latest historical interval: <strong>{latestLabel}</strong>
            {latestAge ? ` (${latestAge})` : ""}. This is the newest aggregated
            bucket in the selected series, not a warehouse refresh timestamp.
          </p>
        )}
        {liveReading && (
          <p className="summary-live">
            Live now:{" "}
            <strong>
              {formatValue(liveReading).number}
              {formatValue(liveReading).suffix
                ? ` ${formatValue(liveReading).suffix}`
                : ""}
            </strong>{" "}
            — distinct from the period statistics above.
          </p>
        )}
      </div>
    </div>
  );
}
