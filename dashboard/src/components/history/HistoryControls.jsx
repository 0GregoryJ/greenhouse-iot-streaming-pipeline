import { PERIOD_LABELS } from "../../lib/format.js";
import { metricInfo } from "../../lib/metrics.js";

const PERIODS = ["24h", "7d", "30d"];

export function HistoryControls({
  sensors,
  measurements,
  sensorId,
  measurementType,
  period,
  onSensorChange,
  onMeasurementChange,
  onPeriodChange,
  disabled,
}) {
  return (
    <div className="history-controls" role="group" aria-label="History filters">
      <label className="control">
        <span className="control-label">Sensor</span>
        <select
          value={sensorId ?? ""}
          onChange={(event) => onSensorChange(event.target.value)}
          disabled={disabled || sensors.length === 0}
        >
          {sensors.length === 0 && <option value="">No sensors found</option>}
          {sensors.map((id) => (
            <option key={id} value={id}>
              {id}
            </option>
          ))}
        </select>
      </label>

      <label className="control">
        <span className="control-label">Measurement</span>
        <select
          value={measurementType ?? ""}
          onChange={(event) => onMeasurementChange(event.target.value)}
          disabled={disabled || measurements.length === 0}
        >
          {measurements.length === 0 && (
            <option value="">No measurements</option>
          )}
          {measurements.map((type) => (
            <option key={type} value={type}>
              {metricInfo(type).label}
            </option>
          ))}
        </select>
      </label>

      <div className="control control-period">
        <span className="control-label" id="period-label">
          Period
        </span>
        <div
          className="segmented"
          role="radiogroup"
          aria-labelledby="period-label"
        >
          {PERIODS.map((value) => (
            <button
              key={value}
              type="button"
              role="radio"
              aria-checked={period === value}
              className={
                period === value ? "segment is-active" : "segment"
              }
              onClick={() => onPeriodChange(value)}
              disabled={disabled}
            >
              {PERIOD_LABELS[value] ?? value}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
