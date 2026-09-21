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
  stackgroup?: string;
  hovertemplate?: string | string[];
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
  let output = data.series.map((series) => ({
    type: "scatter",
    mode,
    name: series.name,
    x: series.x,
    y: series.y,
    // Omit the `marker` key entirely rather than setting it to `undefined`:
    // plotly.js's trace cleanup (plot_api/helpers.js) checks `'marker' in
    // trace`, which is true even for an `undefined` value, then dereferences
    // `trace.marker.line` and throws.
    ...(series.size ? { marker: { size: series.size } } : {}),
    fill: series.stackgroup ? "tonexty" : series.fill ?? defaultFill,
    stackgroup: series.stackgroup,
    hovertemplate: series.hovertemplate ?? ""
  }));

  if (output.length > 0) output[0].fill = output[0].stackgroup ? "tozeroy" : output[0].fill;

  return output
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
