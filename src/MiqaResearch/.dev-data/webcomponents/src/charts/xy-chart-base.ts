import { MiresChartBase } from "./mires-chart-base.js";
import type { PlotlyTrace } from "./chart-types.js";

/**
 * XY line-family Chart Data (docs/charts-handoff.md §7.1): shared by line,
 * scatter, bubble, and filled area, which are all plotly.js's `scatter`
 * trace type distinguished only by `mode` and `fill`. No `color` field —
 * colors always come from the Chart Palette's categorical colorway in series
 * order, never an API-supplied hex (see CONTEXT.md ADR 0022).
 */
export interface XYSeries {
  name: string;
  x: (number | string)[];
  y: number[];
  /** Bubble only — marker size per point. */
  size?: number[];
  /** Filled area only; the other 3 types default to "none". */
  fill?: "none" | "tozeroy" | "tonexty";
}

export interface XYChartData {
  series: XYSeries[];
}

export type XYMode = "lines" | "markers" | "lines+markers";

export function buildXYTraces(
  data: XYChartData,
  mode: XYMode,
  defaultFill: "none" | "tozeroy" | "tonexty" = "none",
): PlotlyTrace[] {
  return data.series.map((series) => ({
    type: "scatter",
    mode,
    name: series.name,
    x: series.x,
    y: series.y,
    marker: series.size ? { size: series.size } : undefined,
    fill: series.fill ?? defaultFill,
  }));
}

export const buildLineTraces = (data: XYChartData): PlotlyTrace[] => buildXYTraces(data, "lines");
export const buildScatterTraces = (data: XYChartData): PlotlyTrace[] => buildXYTraces(data, "markers");
export const buildBubbleTraces = (data: XYChartData): PlotlyTrace[] => buildXYTraces(data, "markers");
export const buildFilledAreaTraces = (data: XYChartData): PlotlyTrace[] => buildXYTraces(data, "lines", "tozeroy");

/**
 * Shared intermediate base for the XY line-family — each concrete element
 * only fixes its own `mode`/default fill; the x/y-array-to-trace mapping is
 * implemented once here.
 */
export abstract class XYChartBase extends MiresChartBase<XYChartData> {
  protected abstract get mode(): XYMode;

  protected get defaultFill(): "none" | "tozeroy" | "tonexty" {
    return "none";
  }

  protected buildTraces(data: XYChartData): PlotlyTrace[] {
    const pointCount = data.series.reduce((total, series) => total + series.x.length, 0);
    return buildXYTraces(data, this.mode, this.defaultFill).map((trace) => ({
      ...trace,
      type: this.maybeUpgradeTraceType("scatter", pointCount),
    }));
  }
}
