import { useEffect, useMemo, useRef, useState } from "react";
import { fetchHistoricalSeries } from "../services/historyApi.js";
import {
  buildInsights,
  fillTimeline,
  summarizePoints,
} from "../lib/historyStats.js";

export function useHistoricalSeries({
  sensorId,
  measurementType,
  period,
  enabled = true,
}) {
  const requestKey =
    enabled && sensorId && measurementType && period
      ? `${sensorId}|${measurementType}|${period}`
      : null;

  const [series, setSeries] = useState(null);
  const [fetchStatus, setFetchStatus] = useState("idle");
  const [error, setError] = useState(null);
  const [activeKey, setActiveKey] = useState(null);
  const abortRef = useRef(null);

  useEffect(() => {
    if (!requestKey) {
      return undefined;
    }

    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    const [nextSensorId, nextMeasurementType, nextPeriod] =
      requestKey.split("|");

    setFetchStatus("loading");
    setError(null);
    setActiveKey(requestKey);

    fetchHistoricalSeries(
      {
        sensorId: nextSensorId,
        measurementType: nextMeasurementType,
        period: nextPeriod,
      },
      controller.signal
    )
      .then((data) => {
        if (controller.signal.aborted) return;
        setSeries(data);
        setFetchStatus("ok");
        setActiveKey(requestKey);
      })
      .catch((err) => {
        if (err?.name === "AbortError") return;
        setSeries(null);
        setFetchStatus("error");
        setError(err instanceof Error ? err.message : "Failed to load history");
        setActiveKey(requestKey);
      });

    return () => controller.abort();
  }, [requestKey]);

  const status = !requestKey
    ? "idle"
    : activeKey === requestKey
      ? fetchStatus
      : "loading";

  const points = activeKey === requestKey ? series?.points : undefined;
  const resolution =
    (activeKey === requestKey ? series?.resolution : null) ??
    (period === "30d" ? "day" : "hour");

  const summary = useMemo(() => summarizePoints(points ?? []), [points]);
  const insights = useMemo(
    () => buildInsights(points ?? [], summary),
    [points, summary]
  );
  const chartData = useMemo(
    () => fillTimeline(points ?? [], period, resolution),
    [points, period, resolution]
  );

  return {
    series: activeKey === requestKey ? series : null,
    points: points ?? [],
    resolution,
    summary,
    insights,
    chartData,
    status,
    error: activeKey === requestKey ? error : null,
  };
}
