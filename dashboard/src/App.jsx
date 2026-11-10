import { lazy, Suspense, useEffect, useState } from "react";
import "./App.css";
import { LiveView } from "./components/live/LiveView.jsx";
import { useLiveReadings } from "./hooks/useLiveReadings.js";

const HistoryView = lazy(() =>
  import("./components/history/HistoryView.jsx").then((module) => ({
    default: module.HistoryView,
  }))
);

const TABS = [
  { id: "live", label: "Live" },
  { id: "history", label: "History" },
];

function App() {
  const [tab, setTab] = useState("live");
  const [now, setNow] = useState(() => Date.now());
  const { readings, status, error, lastFetchedAt } = useLiveReadings({
    enabled: true,
  });

  useEffect(() => {
    const tick = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(tick);
  }, []);

  return (
    <div className="page">
      <header className="top">
        <div>
          <h1>Greenhouse</h1>
          <p className="subtitle">
            {tab === "live"
              ? "Live sensor readings"
              : "Historical environmental trends"}
          </p>
        </div>

        <nav className="tabs" aria-label="Dashboard views">
          {TABS.map((item) => (
            <button
              key={item.id}
              type="button"
              className={tab === item.id ? "tab is-active" : "tab"}
              aria-pressed={tab === item.id}
              onClick={() => setTab(item.id)}
            >
              {item.label}
            </button>
          ))}
        </nav>
      </header>

      {tab === "live" ? (
        <LiveView
          readings={readings}
          status={status}
          error={error}
          lastFetchedAt={lastFetchedAt}
          now={now}
        />
      ) : (
        <Suspense
          fallback={
            <div className="chart-shell chart-shell-loading" aria-busy="true">
              <div className="chart-skeleton" />
              <p>Loading historical analytics…</p>
            </div>
          }
        >
          <HistoryView readings={readings} now={now} />
        </Suspense>
      )}
    </div>
  );
}

export default App;
