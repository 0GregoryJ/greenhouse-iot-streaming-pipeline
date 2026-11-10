import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  formatChartTick,
  formatChartTooltipTime,
  formatValue,
} from "../../lib/format.js";
import { metricInfo } from "../../lib/metrics.js";

function HistoryTooltip({ active, payload, resolution, unit }) {
  if (!active || !payload?.length) return null;

  const row = payload[0]?.payload;
  if (!row || row.missing) {
    return (
      <div className="chart-tooltip">
        <p className="chart-tooltip-time">
          {row?.timestamp
            ? formatChartTooltipTime(row.timestamp, resolution)
            : "Unknown"}
        </p>
        <p className="chart-tooltip-empty">No readings in this interval</p>
      </div>
    );
  }

  const avg = formatValue({ value: row.avg, unit: unit ?? row.unit });
  const min = formatValue({ value: row.min, unit: unit ?? row.unit });
  const max = formatValue({ value: row.max, unit: unit ?? row.unit });
  const lowSample = Number(row.count) > 0 && Number(row.count) < 10;

  return (
    <div className="chart-tooltip">
      <p className="chart-tooltip-time">
        {formatChartTooltipTime(row.timestamp, resolution)}
      </p>
      <dl className="chart-tooltip-stats">
        <div>
          <dt>Average</dt>
          <dd>
            {avg.number}
            {avg.suffix ? ` ${avg.suffix}` : ""}
          </dd>
        </div>
        <div>
          <dt>Min</dt>
          <dd>
            {min.number}
            {min.suffix ? ` ${min.suffix}` : ""}
          </dd>
        </div>
        <div>
          <dt>Max</dt>
          <dd>
            {max.number}
            {max.suffix ? ` ${max.suffix}` : ""}
          </dd>
        </div>
        <div>
          <dt>Readings</dt>
          <dd>
            {Number(row.count).toLocaleString()}
            {lowSample ? " (sparse)" : ""}
          </dd>
        </div>
      </dl>
    </div>
  );
}

export function HistoryChart({
  data,
  resolution,
  unit,
  measurementType,
  status,
}) {
  const label = metricInfo(measurementType).label;
  const rows = data ?? [];
  const present = rows.filter((row) => !row.missing);
  const tickEvery = resolution === "day" ? 5 : rows.length > 48 ? 12 : 4;

  if (status === "loading") {
    return (
      <div className="chart-shell chart-shell-loading" aria-busy="true">
        <div className="chart-skeleton" />
        <p>Loading historical trend…</p>
      </div>
    );
  }

  if (status === "error") {
    return null;
  }

  if (present.length === 0) {
    return (
      <div className="chart-shell chart-shell-empty">
        <p>No historical points for this selection.</p>
        <p className="muted">
          Try another period, or confirm this sensor reported during the window.
        </p>
      </div>
    );
  }

  return (
    <div className="chart-shell">
      <div className="chart-head">
        <h3 className="section-heading">{label} over time</h3>
        <p className="chart-legend">
          <span className="legend-swatch legend-avg" /> Average
          <span className="legend-swatch legend-range" /> Min–max range
        </p>
      </div>

      <div className="chart-frame" role="img" aria-label={`${label} historical trend`}>
        <ResponsiveContainer width="100%" height={320}>
          <ComposedChart
            data={rows}
            margin={{ top: 8, right: 12, left: 0, bottom: 0 }}
          >
            <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" vertical={false} />
            <XAxis
              dataKey="timestamp"
              tickFormatter={(value) => formatChartTick(value, resolution)}
              minTickGap={28}
              interval={tickEvery}
              tick={{ fill: "var(--muted)", fontSize: 12 }}
              axisLine={{ stroke: "var(--border)" }}
              tickLine={false}
            />
            <YAxis
              domain={["auto", "auto"]}
              width={56}
              tick={{ fill: "var(--muted)", fontSize: 12 }}
              axisLine={false}
              tickLine={false}
              tickFormatter={(value) => {
                const formatted = formatValue({ value, unit });
                return formatted.number;
              }}
            />
            <Tooltip
              content={
                <HistoryTooltip resolution={resolution} unit={unit} />
              }
            />
            <Area
              type="monotone"
              dataKey="rangeBase"
              stackId="band"
              stroke="none"
              fill="transparent"
              connectNulls={false}
              isAnimationActive={false}
            />
            <Area
              type="monotone"
              dataKey="rangeSpan"
              stackId="band"
              stroke="none"
              fill="var(--live)"
              fillOpacity={0.18}
              connectNulls={false}
              isAnimationActive={false}
              name="Range"
            />
            <Line
              type="monotone"
              dataKey="avg"
              stroke="var(--live)"
              strokeWidth={2.25}
              dot={false}
              activeDot={{ r: 4, fill: "var(--live)" }}
              connectNulls={false}
              isAnimationActive={false}
              name="Average"
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      <p className="chart-note">
        Gaps are intervals with no warehouse data. Sparse intervals (few
        readings) still plot but are called out in the tooltip.
      </p>
    </div>
  );
}
