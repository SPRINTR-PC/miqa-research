import { customElement } from "lit/decorators.js";
import type { Layout } from "plotly.js";

import { gridCellDomain, gridCellIndex, resolveSubplotIndexFromEvent } from "./chart-grid-utils.js";
import { MiresChartBase } from "./mires-chart-base.js";
import { buildBarTraces } from "./mires-chart-bar.js";
import type { BarChartConfig, BarChartData } from "./mires-chart-bar.js";
import { buildBoxTraces } from "./mires-chart-box.js";
import type { BoxChartConfig, BoxChartData } from "./mires-chart-box.js";
import { buildDensity2DTraces } from "./mires-chart-density-2d.js";
import type { Density2DChartConfig, Density2DChartData } from "./mires-chart-density-2d.js";
import { buildHeatmapTraces } from "./mires-chart-heatmap.js";
import type { HeatmapChartConfig, HeatmapChartData } from "./mires-chart-heatmap.js";
import { buildHistogramTraces } from "./mires-chart-histogram.js";
import type { HistogramChartConfig, HistogramChartData } from "./mires-chart-histogram.js";
import { buildPieTraces } from "./mires-chart-pie.js";
import type { PieChartConfig, PieChartData } from "./mires-chart-pie.js";
import { buildSankeyTraces } from "./mires-chart-sankey.js";
import type { SankeyChartConfig, SankeyChartData } from "./mires-chart-sankey.js";
import { buildBubbleTraces, buildFilledAreaTraces, buildLineTraces, buildScatterTraces } from "./xy-chart-base.js";
import type { XYChartData } from "./xy-chart-base.js";
import type { ChartCallbackEvent, ChartConfig, PlotlyTrace } from "./chart-types.js";

/**
 * Mixed-type Chart Grid Data/Config (docs/charts-handoff.md §8): one combined
 * envelope drives every subplot — a single Grouping switch re-renders all of
 * them together, with no per-subplot Grouping of its own. `subplots[i]` in
 * both Config and Data is positional, sharing one order.
 */
export interface ChartGridSubplotSpec {
  /** Matches a chart-type element's own `chartType` string (e.g. "bar", "filled-area"). */
  type: string;
  row: number;
  col: number;
  config?: unknown;
}

export interface ChartGridConfig extends ChartConfig {
  rows: number;
  cols: number;
  subplots: ChartGridSubplotSpec[];
}

export interface ChartGridData {
  /** One entry per subplot, same order as `ChartGridConfig.subplots`, shaped per that subplot's own type. */
  subplots: unknown[];
}

/** Resolved Chart Palette colors passed to whichever subplot builders need them — keeps every builder pure (ADR 0023). */
export interface ChartGridPaletteColors {
  sequential: string[];
  diverging: [negative: string, neutral: string, positive: string];
  sankeyNodeDefault: string;
}

/** A subplot of this type is positioned via `domain` fractions (§8), not a shared `xaxis`/`yaxis` pair. */
const AXIS_LESS_TYPES = new Set(["pie", "sankey"]);

type SubplotBuilder = (data: unknown, config: unknown, colors: ChartGridPaletteColors) => PlotlyTrace[];

/**
 * Dispatches to the exact same exported pure trace-builder function every
 * single-type element uses (ADR 0023) — no duplicated trace-construction
 * logic. None call `maybeUpgradeTraceType`: that upgrade is a `MiresChartBase`
 * instance method keyed off *this* element's own single `chartType` (§5),
 * which is meaningless for a grid mixing several subplot types, so a
 * WebGL-capable subplot (line/scatter/bubble/filled-area) never upgrades
 * inside a grid — a known limitation carried over from this element's own
 * §8 design, not a per-type oversight.
 */
const TYPE_BUILDERS: Record<string, SubplotBuilder> = {
  bar: (data, config) => buildBarTraces(data as BarChartData, config as BarChartConfig | undefined),
  line: (data) => buildLineTraces(data as XYChartData),
  scatter: (data) => buildScatterTraces(data as XYChartData),
  bubble: (data) => buildBubbleTraces(data as XYChartData),
  "filled-area": (data) => buildFilledAreaTraces(data as XYChartData),
  histogram: (data, config) =>
    buildHistogramTraces(data as HistogramChartData, config as HistogramChartConfig | undefined),
  pie: (data, config) => buildPieTraces(data as PieChartData, config as PieChartConfig | undefined),
  box: (data, config) => buildBoxTraces(data as BoxChartData, config as BoxChartConfig | undefined),
  heatmap: (data, config, colors) =>
    buildHeatmapTraces(data as HeatmapChartData, config as HeatmapChartConfig | undefined, {
      sequential: colors.sequential,
      diverging: colors.diverging,
    }),
  "density-2d": (data, config, colors) =>
    buildDensity2DTraces(data as Density2DChartData, config as Density2DChartConfig | undefined, {
      sequential: colors.sequential,
    }),
  sankey: (data, config, colors) =>
    buildSankeyTraces(data as SankeyChartData, config as SankeyChartConfig | undefined, colors.sankeyNodeDefault),
};

export interface ChartGridTraceResult {
  traces: PlotlyTrace[];
  /** Parallel to `traces` — the `config.subplots` index each trace belongs to, used to attribute a fired click event back to its subplot. */
  traceSubplotIndices: number[];
}

/**
 * Pure trace-assembly for the whole grid (docs/charts-handoff.md §8): each
 * subplot's own builder runs unmodified, and its traces are tagged either
 * with a `domain` (axis-less types) or a per-subplot `xaxis`/`yaxis` pair
 * (every other type) so `layout.grid` can lay them out independently.
 * `axisSuffix` is derived from the subplot's own `row`/`col` grid position
 * via `gridCellIndex` (cell 0 → unsuffixed `x`/`y`, i.e. axis 1) — matching
 * how `layout.grid` itself numbers its auto-generated per-cell axes (by
 * row-major cell position, not by the order subplots happen to appear in
 * `config.subplots`) — rather than the subplot's array index, which would
 * only coincidentally agree when subplots happen to be listed in row-major
 * order.
 */
export function buildChartGridTraces(
  data: ChartGridData,
  config: ChartGridConfig,
  colors: ChartGridPaletteColors,
): ChartGridTraceResult {
  const traces: PlotlyTrace[] = [];
  const traceSubplotIndices: number[] = [];

  config.subplots.forEach((spec, i) => {
    const builder = TYPE_BUILDERS[spec.type];
    if (!builder) {
      console.warn(`<mires-chart-grid>: unknown subplot type "${spec.type}"`);
      return;
    }
    const cellIndex = gridCellIndex(spec.row, spec.col, config.cols);
    const axisSuffix = cellIndex === 0 ? "" : String(cellIndex + 1);
    const subplotTraces = builder(data.subplots[i], spec.config, colors);
    for (const trace of subplotTraces) {
      traces.push(
        AXIS_LESS_TYPES.has(spec.type)
          ? { ...trace, domain: gridCellDomain(spec.row, spec.col, config.rows, config.cols) }
          : { ...trace, xaxis: `x${axisSuffix}`, yaxis: `y${axisSuffix}` },
      );
      traceSubplotIndices.push(i);
    }
  });

  return { traces, traceSubplotIndices };
}

@customElement("mires-chart-grid")
export class MiresChartGrid extends MiresChartBase<ChartGridData> {
  /** Parallel to the last-rendered trace array — rebuilt every `buildTraces` call, read back by `fireCallback` on the next event. */
  private traceSubplotIndices: number[] = [];

  private get gridConfig(): ChartGridConfig | undefined {
    return this.response?.config as ChartGridConfig | undefined;
  }

  private resolvePaletteColors(): ChartGridPaletteColors {
    return {
      sequential: [0, 1, 2, 3, 4, 5].map((i) => this.resolveThemeColor(`--mires-chart-sequential-${i}`)),
      diverging: [
        this.resolveThemeColor("--mires-chart-diverging-negative"),
        this.resolveThemeColor("--mires-chart-diverging-neutral"),
        this.resolveThemeColor("--mires-chart-diverging-positive"),
      ],
      sankeyNodeDefault: this.resolveThemeColor("--mires-chart-sankey-node"),
    };
  }

  protected override buildTraces(data: ChartGridData): PlotlyTrace[] {
    const config = this.gridConfig;
    if (!config) {
      this.traceSubplotIndices = [];
      return [];
    }
    const { traces, traceSubplotIndices } = buildChartGridTraces(data, config, this.resolvePaletteColors());
    this.traceSubplotIndices = traceSubplotIndices;
    return traces;
  }

  protected override extraLayout(): Partial<Layout> {
    const config = this.gridConfig;
    if (!config) {
      return {};
    }
    return { grid: { rows: config.rows, columns: config.cols, pattern: "independent" } };
  }

  /**
   * A mixed-subplot grid cannot mix Chart Groupings across its subplots
   * (§8) — one combined event stream, attributed here to whichever specific
   * subplot fired it via `contextOverride` rather than reporting `"grid"`.
   */
  protected override fireCallback(event: ChartCallbackEvent, raw: unknown): void {
    const config = this.gridConfig;
    const subplotIndex = resolveSubplotIndexFromEvent(event, raw, this.traceSubplotIndices, config);
    const spec = subplotIndex !== undefined ? config?.subplots[subplotIndex] : undefined;
    super.fireCallback(event, raw, { chartType: spec?.type });
  }
}
