export const STALE_AFTER_MS = 30_000;

export function formatValue({ value, unit }) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return { number: "—", suffix: unit ?? "" };
  }

  const n = Number(value);

  switch (unit) {
    case "celsius":
      return { number: n.toFixed(1), suffix: "°C" };
    case "percent":
      return { number: n.toFixed(1), suffix: "%" };
    case "hpa":
      return { number: n.toFixed(1), suffix: "hPa" };
    case "raw_capacitance":
      return { number: Math.round(n).toString(), suffix: "raw" };
    default:
      return {
        number: Number.isInteger(n) ? String(n) : n.toFixed(2),
        suffix: unit ?? "",
      };
  }
}

export function formatValueText(reading) {
  const { number, suffix } = formatValue(reading);
  return suffix ? `${number} ${suffix}` : number;
}

export function ageMs(timestamp, now) {
  const eventTime = new Date(timestamp).getTime();

  if (!Number.isFinite(eventTime)) return null;

  return Math.max(0, now - eventTime);
}

export function isStale(timestamp, now) {
  const age = ageMs(timestamp, now);

  return age === null || age > STALE_AFTER_MS;
}

export function formatAge(age) {
  if (age === null || age === undefined || !Number.isFinite(age)) {
    return "unknown";
  }

  const seconds = Math.floor(age / 1000);

  if (seconds < 5) return "just now";
  if (seconds < 60) return `${seconds}s ago`;

  const minutes = Math.floor(seconds / 60);

  if (minutes < 60) return `${minutes}m ago`;

  return `${Math.floor(minutes / 60)}h ago`;
}

/** Chart / tooltip labels for UTC timestamps. */
export function formatChartTick(iso, resolution) {
  const date = new Date(iso);

  if (!Number.isFinite(date.getTime())) return "";

  if (resolution === "day") {
    return date.toLocaleDateString(undefined, {
      month: "short",
      day: "numeric",
      timeZone: "UTC",
    });
  }

  return date.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    timeZone: "UTC",
    hour12: false,
  });
}

export function formatChartTooltipTime(iso, resolution) {
  const date = new Date(iso);

  if (!Number.isFinite(date.getTime())) return "Unknown time";

  if (resolution === "day") {
    return date.toLocaleDateString(undefined, {
      weekday: "short",
      month: "short",
      day: "numeric",
      year: "numeric",
      timeZone: "UTC",
    }) + " UTC";
  }

  return (
    date.toLocaleString(undefined, {
      weekday: "short",
      month: "short",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit",
      timeZone: "UTC",
      hour12: false,
    }) + " UTC"
  );
}

export const PERIOD_LABELS = {
  "24h": "Last 24 hours",
  "7d": "Last 7 days",
  "30d": "Last 30 days",
};
