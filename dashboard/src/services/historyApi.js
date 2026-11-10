import { HISTORY_SERIES_URL } from "../api/config.js";

const ALLOWED_PERIODS = new Set(["24h", "7d", "30d"]);

/**
 * Fetch aggregated historical series for one sensor + measurement + period.
 */
export async function fetchHistoricalSeries(
  { sensorId, measurementType, period },
  signal
) {
  if (!sensorId || !measurementType) {
    throw new Error("sensor_id and measurement_type are required");
  }

  if (!ALLOWED_PERIODS.has(period)) {
    throw new Error(`Unsupported period: ${period}`);
  }

  const url = new URL(HISTORY_SERIES_URL);

  url.searchParams.set("sensor_id", sensorId);
  url.searchParams.set("measurement_type", measurementType);
  url.searchParams.set("period", period);

  const response = await fetch(url, { signal });

  if (!response.ok) {
    let detail = `History API error ${response.status}`;

    try {
      const body = await response.json();
      if (body?.detail) {
        detail =
          typeof body.detail === "string"
            ? body.detail
            : JSON.stringify(body.detail);
      }
    } catch {
      // keep status-based message
    }

    throw new Error(detail);
  }

  const data = await response.json();

  if (!data || typeof data !== "object" || !Array.isArray(data.points)) {
    throw new Error("History API returned an unexpected payload");
  }

  return data;
}
