import { formatValue } from "./format.js";

/**
 * Weighted average of aggregated points: sum(avg * count) / sum(count).
 * Min/max are extrema of the point-level min/max fields.
 */
export function summarizePoints(points) {
  if (!Array.isArray(points) || points.length === 0) {
    return {
      weightedAvg: null,
      min: null,
      max: null,
      totalReadings: 0,
      intervalCount: 0,
      firstTimestamp: null,
      latestTimestamp: null,
      unit: null,
    };
  }

  let weightedSum = 0;
  let totalReadings = 0;
  let min = Number.POSITIVE_INFINITY;
  let max = Number.NEGATIVE_INFINITY;
  const units = new Set();

  for (const point of points) {
    const count = Number(point.count) || 0;
    const avg = Number(point.avg);
    const pointMin = Number(point.min);
    const pointMax = Number(point.max);

    if (count > 0 && Number.isFinite(avg)) {
      weightedSum += avg * count;
      totalReadings += count;
    }

    if (Number.isFinite(pointMin)) min = Math.min(min, pointMin);
    if (Number.isFinite(pointMax)) max = Math.max(max, pointMax);
    if (point.unit) units.add(point.unit);
  }

  return {
    weightedAvg: totalReadings > 0 ? weightedSum / totalReadings : null,
    min: Number.isFinite(min) ? min : null,
    max: Number.isFinite(max) ? max : null,
    totalReadings,
    intervalCount: points.length,
    firstTimestamp: points[0]?.timestamp ?? null,
    latestTimestamp: points[points.length - 1]?.timestamp ?? null,
    unit: units.size === 1 ? [...units][0] : null,
  };
}

export function buildInsights(points, summary) {
  if (!points?.length || !summary) return [];

  const insights = [];
  const unit = summary.unit;

  const lowest = points.reduce((best, point) =>
    point.min < best.min ? point : best
  );
  const highest = points.reduce((best, point) =>
    point.max > best.max ? point : best
  );

  insights.push({
    key: "low",
    label: "Lowest interval",
    detail: formatInsightValue(lowest.min, unit),
    meta: lowest.timestamp,
  });

  insights.push({
    key: "high",
    label: "Highest interval",
    detail: formatInsightValue(highest.max, unit),
    meta: highest.timestamp,
  });

  const first = points[0];
  const last = points[points.length - 1];

  if (
    first &&
    last &&
    first !== last &&
    Number.isFinite(first.avg) &&
    Number.isFinite(last.avg)
  ) {
    const delta = last.avg - first.avg;
    const direction =
      Math.abs(delta) < 1e-9
        ? "unchanged"
        : delta > 0
          ? "higher"
          : "lower";

    insights.push({
      key: "change",
      label: "Start → end of period",
      detail:
        direction === "unchanged"
          ? "No change between first and last intervals"
          : `${formatInsightValue(Math.abs(delta), unit)} ${direction}`,
      meta: "Compares the first and last aggregated intervals, not a live reading",
    });
  }

  return insights;
}

function formatInsightValue(value, unit) {
  const { number, suffix } = formatValue({ value, unit });
  return suffix ? `${number} ${suffix}` : number;
}

/**
 * Align sparse API points onto a regular UTC grid so chart gaps stay visible.
 * Missing buckets become null values (Recharts connectNulls={false}).
 */
export function fillTimeline(points, period, resolution, now = Date.now()) {
  const byKey = new Map();

  for (const point of points ?? []) {
    const key = normalizeBucketKey(point.timestamp, resolution);
    if (key) byKey.set(key, point);
  }

  const buckets = expectedBuckets(period, resolution, now);

  return buckets.map((bucket) => {
    const point = byKey.get(bucket);

    if (!point) {
      return {
        timestamp: bucket,
        avg: null,
        min: null,
        max: null,
        count: null,
        rangeBase: null,
        rangeSpan: null,
        missing: true,
      };
    }

    const min = Number(point.min);
    const max = Number(point.max);

    return {
      timestamp: bucket,
      avg: Number(point.avg),
      min,
      max,
      count: Number(point.count) || 0,
      unit: point.unit,
      rangeBase: min,
      rangeSpan: Number.isFinite(min) && Number.isFinite(max) ? max - min : null,
      missing: false,
    };
  });
}

export function expectedBuckets(period, resolution, now = Date.now()) {
  const end = new Date(now);

  if (resolution === "day") {
    end.setUTCHours(0, 0, 0, 0);
  } else {
    end.setUTCMinutes(0, 0, 0);
  }

  const hours =
    period === "24h" ? 24 : period === "7d" ? 168 : period === "30d" ? 720 : 168;
  const stepMs = resolution === "day" ? 86_400_000 : 3_600_000;
  const count = resolution === "day" ? Math.ceil(hours / 24) : hours;
  const buckets = [];

  for (let i = count - 1; i >= 0; i -= 1) {
    buckets.push(new Date(end.getTime() - i * stepMs).toISOString().replace(/\.\d{3}Z$/, "Z"));
  }

  return buckets;
}

export function normalizeBucketKey(iso, resolution) {
  const date = new Date(iso);

  if (!Number.isFinite(date.getTime())) return null;

  if (resolution === "day") {
    date.setUTCHours(0, 0, 0, 0);
  } else {
    date.setUTCMinutes(0, 0, 0);
  }

  return date.toISOString().replace(/\.\d{3}Z$/, "Z");
}

/**
 * Build sensor → measurement options from live readings.
 * Historical-only sensors are not discoverable without a metadata endpoint.
 */
export function discoveryFromLiveReadings(readings, sortTypes = (types) => [...types].sort()) {
  const bySensor = new Map();

  for (const reading of readings ?? []) {
    const sensorId = reading.sensor_id;
    const type = reading.measurement_type;

    if (!sensorId || !type) continue;

    if (!bySensor.has(sensorId)) {
      bySensor.set(sensorId, new Set());
    }

    bySensor.get(sensorId).add(type);
  }

  const sensors = [...bySensor.keys()].sort();
  const measurementsBySensor = {};

  for (const sensorId of sensors) {
    measurementsBySensor[sensorId] = sortTypes([...bySensor.get(sensorId)]);
  }

  return { sensors, measurementsBySensor };
}
