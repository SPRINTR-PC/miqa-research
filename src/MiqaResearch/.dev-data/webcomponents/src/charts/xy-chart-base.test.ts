import { describe, expect, it } from "vitest";

import {
  buildBubbleTraces,
  buildFilledAreaTraces,
  buildLineTraces,
  buildScatterTraces,
  buildXYTraces,
  type XYChartData,
} from "./xy-chart-base.js";

describe("buildXYTraces", () => {
  const data: XYChartData = {
    series: [
      { name: "Series A", x: [1, 2, 3], y: [10, 20, 30] },
      { name: "Series B", x: [1, 2, 3], y: [5, 15, 25], size: [4, 8, 12] },
    ],
  };

  it("builds one trace per series with the given mode", () => {
    const traces = buildXYTraces(data, "lines");

    expect(traces).toHaveLength(2);
    expect(traces[0]).toMatchObject({
      type: "scatter",
      mode: "lines",
      name: "Series A",
      x: [1, 2, 3],
      y: [10, 20, 30],
    });
  });

  it("passes bubble size through as marker.size", () => {
    const traces = buildXYTraces(data, "markers");

    expect(traces[1]?.marker).toEqual({ size: [4, 8, 12] });
    expect(traces[0]?.marker).toBeUndefined();
  });

  it("defaults fill to the family default when a series doesn't set one", () => {
    const traces = buildXYTraces(data, "lines", "tozeroy");

    expect(traces[0]?.fill).toBe("tozeroy");
  });

  it("lets a series override the family default fill", () => {
    const withOverride: XYChartData = {
      series: [{ name: "S", x: [1], y: [1], fill: "tonexty" }],
    };

    const traces = buildXYTraces(withOverride, "lines", "tozeroy");

    expect(traces[0]?.fill).toBe("tonexty");
  });

  it("accepts categorical/datetime-string x values alongside numeric ones", () => {
    const withStringX: XYChartData = {
      series: [{ name: "S", x: ["2024-01-01", "2024-01-02"], y: [1, 2] }],
    };

    const traces = buildXYTraces(withStringX, "lines");

    expect(traces[0]?.x).toEqual(["2024-01-01", "2024-01-02"]);
  });
});

describe("buildLineTraces / buildScatterTraces / buildBubbleTraces / buildFilledAreaTraces", () => {
  const data: XYChartData = { series: [{ name: "S", x: [1, 2], y: [1, 2] }] };

  it("buildLineTraces uses lines mode with no fill", () => {
    expect(buildLineTraces(data)[0]).toMatchObject({ mode: "lines", fill: "none" });
  });

  it("buildScatterTraces uses markers mode with no fill", () => {
    expect(buildScatterTraces(data)[0]).toMatchObject({ mode: "markers", fill: "none" });
  });

  it("buildBubbleTraces uses markers mode", () => {
    expect(buildBubbleTraces(data)[0]).toMatchObject({ mode: "markers" });
  });

  it("buildFilledAreaTraces uses lines mode with a tozeroy default fill", () => {
    expect(buildFilledAreaTraces(data)[0]).toMatchObject({ mode: "lines", fill: "tozeroy" });
  });
});
