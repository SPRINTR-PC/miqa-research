import { customElement } from "lit/decorators.js";

import { MiresChartBase } from "./mires-chart-base.js";
import type { ChartConfig, PlotlyTrace } from "./chart-types.js";

/**
 * Histogram Data/Config (docs/charts-handoff.md §7.3): `series[i].values` are
 * raw per-record values — plotly.js bins them client-side. `bins` on a series
 * overrides `HistogramChartConfig.histogramBins`, the chart-wide default.
 */
export interface HistogramBins {
  nbinsx?: number;
  start?: number;
  end?: number;
  size?: number;
}

export interface HistogramSeries {
  name: string;
  values: number[];
  bins?: HistogramBins;
}

export interface HistogramChartData {
  series: HistogramSeries[];
}

export interface HistogramChartConfig extends ChartConfig {
  /** Chart-wide default binning; a series' own `bins` overrides this. */
  histogramBins?: HistogramBins;
  /** Default "v". */
  orientation?: "v" | "h";
  /** Default "" (plotly's own default: raw counts). */
  histnorm?: "" | "percent" | "probability" | "density" | "probability density";
}

export function buildHistogramTraces(
  data: HistogramChartData,
  config?: HistogramChartConfig,
): PlotlyTrace[] {
  const orientation = config?.orientation ?? "v";
  const histnorm = config?.histnorm ?? "";
  return data.series.map((series) => {
    const bins = series.bins ?? config?.histogramBins;
    const binsField =
      bins && orientation === "v"
        ? { nbinsx: bins.nbinsx, xbins: { start: bins.start, end: bins.end, size: bins.size } }
        : bins && orientation === "h"
          ? { nbinsy: bins.nbinsx, ybins: { start: bins.start, end: bins.end, size: bins.size } }
          : {};
    return {
      type: "histogram",
      name: series.name,
      orientation,
      histnorm,
      ...(orientation === "v" ? { x: series.values } : { y: series.values }),
      ...binsField,
    };
  });
}

@customElement("mires-chart-histogram")
export class MiresChartHistogram extends MiresChartBase<HistogramChartData> {
  private get histogramConfig(): HistogramChartConfig | undefined {
    return this.response?.config as HistogramChartConfig | undefined;
  }

  protected override buildTraces(data: HistogramChartData): PlotlyTrace[] {
    return buildHistogramTraces(data, this.histogramConfig).map((trace) => ({
      ...trace,
      type: this.maybeUpgradeTraceType("histogram", 0), // no-op — histogram has no WebGL variant (§5)
    }));
  }
}
