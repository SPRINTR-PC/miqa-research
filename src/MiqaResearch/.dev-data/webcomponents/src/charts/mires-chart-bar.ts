import { customElement } from "lit/decorators.js";
import type { Layout } from "plotly.js";

import { MiresChartBase } from "./mires-chart-base.js";
import type { ChartConfig, PlotlyTrace } from "./chart-types.js";

/**
 * Bar Chart Data (docs/charts-handoff.md §7.2): `series` is aligned
 * positionally with `categories` — `series[i].values[j]` is the bar for
 * `categories[j]`. A single entry in `series` renders a plain (non-grouped,
 * non-stacked) bar chart.
 */
export interface BarSeries {
  name: string;
  values: number[];
}

export interface BarChartData {
  categories: string[];
  series: BarSeries[];
}

export interface BarChartConfig extends ChartConfig {
  /** Named after plotly.js's own `layout.barmode`. Default "group". */
  barMode?: "group" | "stack";
  /** Default "v". */
  orientation?: "v" | "h";
}

export function buildBarTraces(data: BarChartData, config?: BarChartConfig): PlotlyTrace[] {
  const orientation = config?.orientation ?? "v";
  return data.series.map((series) => ({
    type: "bar",
    orientation,
    name: series.name,
    x: orientation === "v" ? data.categories : series.values,
    y: orientation === "v" ? series.values : data.categories,
  }));
}

@customElement("mires-chart-bar")
export class MiresChartBar extends MiresChartBase<BarChartData> {
  private get barConfig(): BarChartConfig | undefined {
    return this.response?.config as BarChartConfig | undefined;
  }

  protected override buildTraces(data: BarChartData): PlotlyTrace[] {
    return buildBarTraces(data, this.barConfig).map((trace) => ({
      ...trace,
      type: this.maybeUpgradeTraceType("bar", 0), // no-op — bar has no WebGL variant (§5)
    }));
  }

  protected override extraLayout(): Partial<Layout> {
    return { barmode: this.barConfig?.barMode ?? "group" };
  }
}
