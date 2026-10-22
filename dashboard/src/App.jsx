import { useEffect, useState } from "react";

const API_URL =
  "https://api.gregoryjoshua.com/api/v1/sensors/latest";

const STALE_AFTER_MS = 30_000;

function isStale(timestamp) {
  if (!timestamp) return true;

  const eventTime = new Date(timestamp).getTime();

  if (!Number.isFinite(eventTime)) return true;

  return Date.now() - eventTime > STALE_AFTER_MS;
}

function App() {
  const [readings, setReadings] = useState([]);
  const [error, setError] = useState(null);

  useEffect(() => {
    async function fetchReadings() {
      try {
        const response = await fetch(API_URL);

        if (!response.ok) {
          throw new Error(`API returned ${response.status}`);
        }

        const data = await response.json();
        setReadings(data.readings);
        setError(null);
      } catch (err) {
        setError(err.message);
      }
    }

    // Fetch immediately.
    fetchReadings();

    // Refresh every 3 seconds.
    const interval = setInterval(fetchReadings, 3000);

    // Clean up when the component unmounts.
    return () => clearInterval(interval);
  }, []);

  return (
    <div>
      <h1>Greenhouse Live Monitor</h1>

      {error && <p>API Error: {error}</p>}

      {readings.map((reading) => {
        const stale = isStale(reading.timestamp);

        return (
          <div key={`${reading.sensor_id}-${reading.measurement_type}`}>
            <h3>{reading.measurement_type}</h3>
            <p>{reading.value} {reading.unit}</p>

            <span className={stale ? "status stale" : "status online"}>
              {stale ? "Stale" : "Live"}
            </span>
          </div>
        );
      })}
    </div>
  );
}

export default App;