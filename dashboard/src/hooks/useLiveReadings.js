import { useCallback, useEffect, useRef, useState } from "react";
import { fetchLatestReadings } from "../services/liveApi.js";

const POLL_MS = 3_000;

export function useLiveReadings({ enabled = true } = {}) {
  const [readings, setReadings] = useState([]);
  const [status, setStatus] = useState("loading");
  const [error, setError] = useState(null);
  const [lastFetchedAt, setLastFetchedAt] = useState(null);
  const abortRef = useRef(null);

  const load = useCallback(async () => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    try {
      const data = await fetchLatestReadings(controller.signal);
      setReadings(data);
      setStatus("ok");
      setError(null);
      setLastFetchedAt(Date.now());
    } catch (err) {
      if (err?.name === "AbortError") return;

      setStatus((prev) => (prev === "ok" ? "ok" : "error"));
      setError(err instanceof Error ? err.message : "Failed to load live readings");
    }
  }, []);

  useEffect(() => {
    if (!enabled) return undefined;

    load();
    const id = window.setInterval(load, POLL_MS);

    return () => {
      window.clearInterval(id);
      abortRef.current?.abort();
    };
  }, [enabled, load]);

  return {
    readings,
    status,
    error,
    lastFetchedAt,
    refresh: load,
  };
}
