import { customElement } from "lit/decorators.js";

import { MiresChartBase } from "./mires-chart-base.js";
import type { ChartConfig, PlotlyTrace } from "./chart-types.js";

/**
 * Pie Chart Data/Config (docs/charts-handoff.md §7.4): FLAT — no `series`
 * wrapper, a pie has exactly one distribution per Chart Grouping. `hole`
 * turns the same component into a donut; there is no separate donut element.
 */
export interface PieChartData {
  labels: string[];
  values: number[];
}

export interface PieChartConfig extends ChartConfig {
  /** 0 (default) = plain pie; e.g. 0.4-0.7 = donut. */
  hole?: number;
  /** Default true (plotly's own default); false preserves array order. */
  sort?: boolean;
  /** Default "label+percent". */
  textinfo?:
    | "label"
    | "value"
    | "percent"
    | "label+percent"
    | "label+value"
    | "value+percent"
    | "label+value+percent"
    | "none";
}

export function buildPieTraces(data: PieChartData, config?: PieChartConfig): PlotlyTrace[] {
  return [
    {
      type: "pie",
      labels: data.labels,
      values: data.values,
      hole: config?.hole ?? 0,
      sort: config?.sort ?? true,
      textinfo: config?.textinfo ?? "label+percent",
    },
  ];
}

@customElement("mires-chart-pie")
export class MiresChartPie extends MiresChartBase<PieChartData> {
  private get pieConfig(): PieChartConfig | undefined {
    return this.response?.config as PieChartConfig | undefined;
  }

  protected override buildTraces(data: PieChartData): PlotlyTrace[] {
    return buildPieTraces(data, this.pieConfig).map((trace) => ({
      ...trace,
      type: this.maybeUpgradeTraceType("pie", 0), // no-op — pie has no WebGL variant (§5)
    }));
  }
}
