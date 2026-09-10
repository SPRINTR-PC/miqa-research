/**
 * Chart Config (CONTEXT.md, ADR 0020): layout/behaviour settings fixed across
 * every Chart Grouping in a response.
 */
export interface ChartConfig {
  webglThreshold?: number;
  forceRenderer?: "svg" | "webgl" | "auto";
  eventCallbacks?: { click?: string; zoom?: string };
  subplot?: unknown; // only meaningful on <mires-chart-grid>
}

export interface ChartGroupingLabels {
  xAxisTitle?: string;
  yAxisTitle?: string;
  legendTitle?: string;
}

/**
 * Chart Grouping (CONTEXT.md): one of possibly several alternative groupings
 * of the same underlying dataset a `dataUrl` response can return.
 */
export interface ChartGrouping<TData> {
  name: string;
  label: string;
  labels?: ChartGroupingLabels;
  data: TData;
}

/**
 * The full response shape returned by a chart component's `dataUrl` endpoint.
 * `groupings` is always a non-empty array, even when there is only one Chart
 * Grouping — the component skips rendering the dropdown at length 1 rather
 * than the API using a distinct single-Grouping shape.
 */
export interface ChartResponse<TConfig, TData> {
  config?: TConfig;
  groupings: ChartGrouping<TData>[];
}

export type ChartCallbackEvent = "click" | "zoom";

/**
 * Chart Event Callback (CONTEXT.md, ADR 0021): the normalized payload passed
 * to a registered callback function.
 */
export interface ChartCallbackPayload {
  chartId: string;
  chartType: string;
  groupingName: string;
  event: ChartCallbackEvent;
  raw: unknown;
}

export type ChartCallback = (payload: ChartCallbackPayload) => void;

/**
 * A permissive stand-in for a single plotly.js trace object during
 * construction. `Plotly.Data`'s real type is a large discriminated union
 * keyed by `type`, which type-checks awkwardly for generic trace-building
 * code that assembles a trace field-by-field (often before its final `type`
 * is known, e.g. before a WebGL-upgrade decision). Cast to `Plotly.Data[]`
 * only at the actual `Plotly.react`/`newPlot` call boundary.
 */
export type PlotlyTrace = Record<string, unknown>;
