/** Display order and labels for known measurement types. */
export const METRICS = {
  air_temperature: { label: "Air temperature", order: 0, primary: true },
  relative_humidity: { label: "Relative humidity", order: 1, primary: true },
  atmospheric_pressure: {
    label: "Atmospheric pressure",
    order: 2,
    primary: false,
  },
  soil_moisture: { label: "Soil moisture", order: 3, primary: true },
  soil_temperature: { label: "Soil temperature", order: 4, primary: true },
};

export function metricInfo(type) {
  if (METRICS[type]) return METRICS[type];

  const label = String(type ?? "Unknown").replace(/_/g, " ");

  return {
    label: label.charAt(0).toUpperCase() + label.slice(1),
    order: Number.MAX_SAFE_INTEGER,
    primary: true,
  };
}

export function sortMeasurementTypes(types) {
  return [...types].sort(
    (a, b) =>
      metricInfo(a).order - metricInfo(b).order ||
      String(a).localeCompare(String(b))
  );
}
