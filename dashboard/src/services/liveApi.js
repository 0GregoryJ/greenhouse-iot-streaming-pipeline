import { LIVE_LATEST_URL } from "../api/config.js";

/**
 * Fetch the latest live readings from Redis-backed FastAPI.
 * Response shape: { count, readings: [...] }
 */
export async function fetchLatestReadings(signal) {
  const response = await fetch(LIVE_LATEST_URL, { signal });

  if (!response.ok) {
    throw new Error(`Live API error ${response.status}`);
  }

  const data = await response.json();
  const readings = Array.isArray(data) ? data : data?.readings;

  if (!Array.isArray(readings)) {
    throw new Error("Live API returned an unexpected payload");
  }

  return readings;
}
