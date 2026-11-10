import { useMemo, useState } from "react";
import { discoveryFromLiveReadings } from "../../lib/historyStats.js";
import { sortMeasurementTypes } from "../../lib/metrics.js";
import { useHistoricalSeries } from "../../hooks/useHistoricalSeries.js";
import { HistoryChart } from "./HistoryChart.jsx";
import { HistoryControls } from "./HistoryControls.jsx";
import { HistoryInsights } from "./HistoryInsights.jsx";
import { HistorySummary } from "./HistorySummary.jsx";

/**
 * Sensor / measurement discovery uses the live latest endpoint.
 * Sensors that only exist in the warehouse (no current Redis key) will not
 * appear here until a dedicated history metadata endpoint exists.
 */
export function HistoryView({ readings, now }) {
  const discovery = useMemo(
    () => discoveryFromLiveReadings(readings, sortMeasurementTypes),
    [readings]
  );

  const [sensorId, setSensorId] = useState("");
  const [measurementType, setMeasurementType] = useState("");
  const [period, setPeriod] = useState("7d");

  const resolvedSensorId =
    sensorId && discovery.sensors.includes(sensorId)
      ? sensorId
      : (discovery.sensors[0] ?? "");

  const measurements =
    discovery.measurementsBySensor[resolvedSensorId] ?? [];

  const resolvedMeasurementType =
    measurementType && measurements.includes(measurementType)
      ? measurementType
      : (measurements[0] ?? "");

  const {
    series,
    resolution,
    summary,
    insights,
    chartData,
    status,
    error,
  } = useHistoricalSeries({
    sensorId: resolvedSensorId,
    measurementType: resolvedMeasurementType,
    period,
    enabled: Boolean(resolvedSensorId && resolvedMeasurementType),
  });

  const liveReading = useMemo(
    () =>
      readings.find(
        (reading) =>
          reading.sensor_id === resolvedSensorId &&
          reading.measurement_type === resolvedMeasurementType
      ) ?? null,
    [readings, resolvedSensorId, resolvedMeasurementType]
  );

  const unit = series?.unit ?? summary.unit ?? liveReading?.unit ?? null;

  return (
    <section className="view history-view" aria-label="Historical analytics">
      <div className="view-toolbar">
        <div>
          <h2 className="view-title">Historical analytics</h2>
          <p className="view-copy">
            Aggregated warehouse trends for greenhouse conditions — hourly for
            24h/7d, daily for 30d.
          </p>
        </div>
        <span className="pill pill-idle">
          <span className="pill-dot" />
          Warehouse
        </span>
      </div>

      <HistoryControls
        sensors={discovery.sensors}
        measurements={measurements}
        sensorId={resolvedSensorId}
        measurementType={resolvedMeasurementType}
        period={period}
        onSensorChange={(next) => {
          setSensorId(next);
          setMeasurementType("");
        }}
        onMeasurementChange={setMeasurementType}
        onPeriodChange={setPeriod}
        disabled={discovery.sensors.length === 0}
      />

      {discovery.sensors.length === 0 && (
        <p className="notice notice-info" role="status">
          No live sensors are available to select from. History discovery uses
          the live endpoint, so warehouse-only sensors cannot be listed yet.
        </p>
      )}

      {error && (
        <p className="notice" role="alert">
          {error}
        </p>
      )}

      {status === "ok" && summary.totalReadings > 0 && (
        <HistorySummary
          summary={summary}
          period={period}
          resolution={resolution}
          unit={unit}
          liveReading={liveReading}
          now={now}
        />
      )}

      <HistoryChart
        data={chartData}
        resolution={resolution}
        unit={unit}
        measurementType={resolvedMeasurementType}
        status={
          discovery.sensors.length === 0
            ? "error"
            : status === "idle"
              ? "loading"
              : status
        }
      />

      {status === "ok" && summary.totalReadings > 0 && (
        <HistoryInsights insights={insights} resolution={resolution} />
      )}
    </section>
  );
}
