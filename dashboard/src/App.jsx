import { useEffect, useState } from "react";

const API_URL =
  "https://api.gregoryjoshua.com/api/v1/sensors/latest";

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

      {readings.map((reading) => (
        <div key={`${reading.sensor_id}-${reading.measurement_type}`}>
          <h2>{reading.measurement_type}</h2>
          <p>
            {reading.value} {reading.unit}
          </p>
          <small>Updated: {reading.timestamp}</small>
        </div>
      ))}
    </div>
  );
}

export default App;