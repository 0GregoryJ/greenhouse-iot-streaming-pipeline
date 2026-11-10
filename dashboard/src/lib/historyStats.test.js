import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  buildInsights,
  expectedBuckets,
  fillTimeline,
  summarizePoints,
} from "./historyStats.js";

describe("summarizePoints", () => {
  it("returns empty summary for no points", () => {
    const summary = summarizePoints([]);

    assert.equal(summary.weightedAvg, null);
    assert.equal(summary.totalReadings, 0);
    assert.equal(summary.intervalCount, 0);
  });

  it("weights averages by reading count", () => {
    const summary = summarizePoints([
      {
        timestamp: "2026-11-08T12:00:00Z",
        avg: 10,
        min: 9,
        max: 11,
        count: 1,
        unit: "celsius",
      },
      {
        timestamp: "2026-11-08T13:00:00Z",
        avg: 20,
        min: 18,
        max: 22,
        count: 3,
        unit: "celsius",
      },
    ]);

    assert.equal(summary.weightedAvg, 17.5);
    assert.equal(summary.min, 9);
    assert.equal(summary.max, 22);
    assert.equal(summary.totalReadings, 4);
    assert.equal(summary.unit, "celsius");
    assert.equal(summary.firstTimestamp, "2026-11-08T12:00:00Z");
    assert.equal(summary.latestTimestamp, "2026-11-08T13:00:00Z");
  });
});

describe("buildInsights", () => {
  it("describes extrema and start-to-end change", () => {
    const points = [
      {
        timestamp: "2026-11-08T12:00:00Z",
        avg: 20,
        min: 19,
        max: 21,
        count: 10,
        unit: "celsius",
      },
      {
        timestamp: "2026-11-08T13:00:00Z",
        avg: 22,
        min: 18,
        max: 24,
        count: 10,
        unit: "celsius",
      },
    ];
    const summary = summarizePoints(points);
    const insights = buildInsights(points, summary);

    assert.equal(insights.length, 3);
    assert.equal(insights[0].key, "low");
    assert.match(insights[0].detail, /18\.0 °C/);
    assert.equal(insights[1].key, "high");
    assert.match(insights[1].detail, /24\.0 °C/);
    assert.equal(insights[2].key, "change");
    assert.match(insights[2].detail, /higher/);
  });
});

describe("fillTimeline", () => {
  it("preserves gaps as null averages", () => {
    const now = Date.parse("2026-11-09T15:00:00.000Z");
    const points = [
      {
        timestamp: "2026-11-09T14:00:00Z",
        avg: 21.5,
        min: 21,
        max: 22,
        count: 5,
        unit: "celsius",
      },
    ];
    const series = fillTimeline(points, "24h", "hour", now);
    const buckets = expectedBuckets("24h", "hour", now);

    assert.equal(series.length, 24);
    assert.equal(buckets.length, 24);

    const filled = series.find((row) => row.timestamp === "2026-11-09T14:00:00Z");
    const gap = series.find((row) => row.timestamp === "2026-11-09T13:00:00Z");

    assert.equal(filled.avg, 21.5);
    assert.equal(filled.missing, false);
    assert.equal(gap.avg, null);
    assert.equal(gap.missing, true);
  });
});
