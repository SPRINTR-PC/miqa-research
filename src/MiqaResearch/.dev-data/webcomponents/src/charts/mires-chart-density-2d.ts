import { customElement } from "lit/decorators.js";

import { MiresChartBase } from "./mires-chart-base.js";
import type { ChartConfig, PlotlyTrace } from "./chart-types.js";

/**
 * 2D Density Data/Config (docs/charts-handoff.md §7.7): `series[i].x`/`.y`
 * are raw scattered point pairs — plotly.js bins them client-side, same
 * raw-values-by-default precedent as histogram. `config.style` toggles the
 * underlying trace type rather than this being two separate elements
 * (mirrors §7.2/§7.4's precedent for closely-related variants). Boundary
 * with heatmap (§7.6): heatmap takes a pre-binned `z` matrix, density takes
 * raw points. Colorscale is sequential-only — density has no polarity
 * concept, unlike heatmap's optional diverging ramp.
 */
export interface Density2DBins {
  nbinsx?: number;
  nbinsy?: number;
  xbins?: { start?: number; end?: number; size?: number };
  ybins?: { start?: number; end?: number; size?: number };
}

export interface Density2DSeries {
  name: string;
  x: number[];
  y: number[];
  /** Overrides `Density2DChartConfig.densityBins`, the chart-wide default. */
  bins?: Density2DBins;
}

export interface Density2DChartData {
  series: Density2DSeries[];
}

export interface Density2DChartConfig extends ChartConfig {
  /** Default "heatmap". */
  style?: "heatmap" | "contour";
  /** Chart-wide default binning; a series' own `bins` overrides this. */
  densityBins?: Density2DBins;
}

/** Resolved Chart Palette colors a trace-builder needs but must not resolve itself (keeps it pure — GLOSSARY.md Chart Palette, ADR 0023). */
export interface Density2DChartColors {
  sequential: string[];
}

export function buildDensity2DTraces(
  data: Density2DChartData,
  config: Density2DChartConfig | undefined,
  colors: Density2DChartColors,
): PlotlyTrace[] {
  const baseType = (config?.style ?? "heatmap") === "contour" ? "histogram2dcontour" : "histogram2d";
  const colorscale = colors.sequential.map((c, i) => [i / (colors.sequential.length - 1), c]);
  return data.series.map((series) => {
    const bins = series.bins ?? config?.densityBins;
    return {
      type: baseType,
      name: series.name,
      x: series.x,
      y: series.y,
      nbinsx: bins?.nbinsx,
      nbinsy: bins?.nbinsy,
      xbins: bins?.xbins,
      ybins: bins?.ybins,
      colorscale,
    };
  });
}

@customElement("mires-chart-density-2d")
export class MiresChartDensity2D extends MiresChartBase<Density2DChartData> {
  private get density2DConfig(): Density2DChartConfig | undefined {
    return this.response?.config as Density2DChartConfig | undefined;
  }

  private resolvePaletteColors(): Density2DChartColors {
    return { sequential: [0, 1, 2, 3, 4, 5].map((i) => this.resolveThemeColor(`--mires-chart-sequential-${i}`)) };
  }

  protected override buildTraces(data: Density2DChartData): PlotlyTrace[] {
    return buildDensity2DTraces(data, this.density2DConfig, this.resolvePaletteColors()).map((trace) => ({
      ...trace,
      type: this.maybeUpgradeTraceType(trace.type as string, 0), // no-op — neither histogram2d nor histogram2dcontour has a WebGL variant (§5/§7.7)
    }));
  }
}
