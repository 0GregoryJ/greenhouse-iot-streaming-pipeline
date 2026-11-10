import { formatChartTooltipTime } from "../../lib/format.js";

export function HistoryInsights({ insights, resolution }) {
  if (!insights?.length) return null;

  return (
    <section className="history-insights" aria-label="Period insights">
      <h3 className="section-heading">What changed</h3>
      <ul className="insight-list">
        {insights.map((insight) => (
          <li key={insight.key} className="insight-item">
            <span className="insight-label">{insight.label}</span>
            <span className="insight-detail">{insight.detail}</span>
            {insight.meta && (
              <span className="insight-meta">
                {insight.key === "change"
                  ? insight.meta
                  : formatChartTooltipTime(insight.meta, resolution)}
              </span>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
