import { customElement } from "lit/decorators.js";

import { MiresChartBase } from "./mires-chart-base.js";
import type { ChartConfig, PlotlyTrace } from "./chart-types.js";

/**
 * Heatmap Chart Data/Config (docs/charts-handoff.md §7.6): `z` is a
 * pre-binned matrix (the server already decided resolution — unlike 2D
 * density, there's no raw-records layer underneath to aggregate). `x`/`y`
 * default to indices when omitted. `colorScale` opts into the fixed
 * diverging ramp (ADR 0022 amendment) for polarity data with a meaningful
 * zero (e.g. a correlation matrix); the default "sequential" ramp is a plain
 * magnitude encoding.
 */
export interface HeatmapChartData {
  z: number[][];
  x?: (number | string)[];
  y?: (number | string)[];
}

export interface HeatmapChartConfig extends ChartConfig {
  /** Default "sequential". */
  colorScale?: "sequential" | "diverging";
  /** Only meaningful for "diverging" — default 0. */
  zMid?: number;
}

/** Resolved Chart Palette colors a trace-builder needs but must not resolve itself (keeps it pure — GLOSSARY.md Chart Palette, ADR 0023). */
export interface HeatmapChartColors {
  sequential: string[];
  diverging: [negative: string, neutral: string, positive: string];
}

export function buildHeatmapTraces(
  data: HeatmapChartData,
  config: HeatmapChartConfig | undefined,
  colors: HeatmapChartColors,
): PlotlyTrace[] {
  const mode = config?.colorScale ?? "sequential";
  const colorscale =
    mode === "diverging"
      ? [
          [0, colors.diverging[0]],
          [0.5, colors.diverging[1]],
          [1, colors.diverging[2]],
        ]
      : colors.sequential.map((c, i) => [i / (colors.sequential.length - 1), c]);

  return [
    {
      type: "heatmap",
      z: data.z,
      x: data.x,
      y: data.y,
      colorscale,
      zmid: mode === "diverging" ? (config?.zMid ?? 0) : undefined,
    },
  ];
}

@customElement("mires-chart-heatmap")
export class MiresChartHeatmap extends MiresChartBase<HeatmapChartData> {
  private get heatmapConfig(): HeatmapChartConfig | undefined {
    return this.response?.config as HeatmapChartConfig | undefined;
  }

  private resolvePaletteColors(): HeatmapChartColors {
    return {
      sequential: [0, 1, 2, 3, 4, 5].map((i) => this.resolveThemeColor(`--mires-chart-sequential-${i}`)),
      diverging: [
        this.resolveThemeColor("--mires-chart-diverging-negative"),
        this.resolveThemeColor("--mires-chart-diverging-neutral"),
        this.resolveThemeColor("--mires-chart-diverging-positive"),
      ],
    };
  }

  protected override buildTraces(data: HeatmapChartData): PlotlyTrace[] {
    return buildHeatmapTraces(data, this.heatmapConfig, this.resolvePaletteColors()).map((trace) => ({
      ...trace,
      type: this.maybeUpgradeTraceType("heatmap", 0), // no-op — heatmapgl removed in plotly.js v3.0.0 (§7.6)
    }));
  }
}
