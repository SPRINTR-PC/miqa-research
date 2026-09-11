import type { ChartCallbackEvent } from "./chart-types.js";

/**
 * Row-major index of a grid cell (docs/charts-handoff.md §8) — this is also
 * the axis number `layout.grid` assigns that cell (1-indexed, unsuffixed for
 * cell 0) when it auto-generates `rows * cols` `xaxis`/`yaxis` pairs, since
 * Plotly numbers grid axes by cell position, not by trace-declaration order.
 * Shared by `buildChartGridTraces` (spec → axis number) and
 * `resolveSubplotIndexFromEvent` (axis number → spec) so both directions of
 * that mapping agree.
 */
export function gridCellIndex(row: number, col: number, cols: number): number {
  return row * cols + col;
}

/**
 * Maps a subplot's `row`/`col` grid position to Plotly `domain` fractions
 * (docs/charts-handoff.md §8) — the only positioning mechanism available to
 * the axis-less chart types (pie, sankey), which can't take part in
 * `layout.grid`'s shared-axis layout. `gutter` is the fraction of each
 * cell's own width/height reserved as a gap between subplots.
 */
export function gridCellDomain(
  row: number,
  col: number,
  rows: number,
  cols: number,
  gutter = 0.08,
): { x: [number, number]; y: [number, number] } {
  const cellWidth = 1 / cols;
  const cellHeight = 1 / rows;
  const padX = (cellWidth * gutter) / 2;
  const padY = (cellHeight * gutter) / 2;
  return {
    x: [col * cellWidth + padX, (col + 1) * cellWidth - padX],
    // row 0 is the top row; Plotly's y domain runs bottom (0) to top (1).
    y: [1 - (row + 1) * cellHeight + padY, 1 - row * cellHeight - padY],
  };
}

/** The minimal grid shape `resolveSubplotIndexFromEvent` needs to reverse a zoom event's axis number back to a subplot. */
export interface ChartGridAxisLookup {
  cols: number;
  subplots: { row: number; col: number }[];
}

/**
 * Maps a fired Plotly click/zoom event back to the grid subplot index that
 * fired it (docs/charts-handoff.md §8), so `<mires-chart-grid>` can attribute
 * the Chart Event Callback to that subplot's own chart type rather than the
 * grid as a whole.
 *
 * `click` events carry `points[0].curveNumber` — an index into the flattened
 * trace array assembled by `buildChartGridTraces` — resolved back to a
 * subplot via `traceSubplotIndices` (parallel to that trace array).
 *
 * `zoom` (`plotly_relayout`) events carry no `points`/`curveNumber` at all;
 * instead the event object's own keys are axis-scoped (e.g.
 * `"xaxis2.range[0]"`, or unsuffixed `"xaxis.range[0]"` for the axis at grid
 * cell 0) — axis-less subplot types (pie, sankey) have no axes to relayout,
 * so a zoom event always names one. The axis number is a *grid-cell*
 * position (`gridCellIndex`), not a `config.subplots` array index, so
 * resolving it back requires searching `gridLookup.subplots` for the one
 * whose `row`/`col` occupies that cell — `gridLookup` is omitted (returning
 * `undefined`) only for a "click"-only caller that has no zoom to resolve.
 */
export function resolveSubplotIndexFromEvent(
  event: ChartCallbackEvent,
  raw: unknown,
  traceSubplotIndices: number[],
  gridLookup?: ChartGridAxisLookup,
): number | undefined {
  if (event === "click") {
    const points = (raw as { points?: { curveNumber?: number }[] } | undefined)?.points;
    const curveNumber = points?.[0]?.curveNumber;
    return curveNumber === undefined ? undefined : traceSubplotIndices[curveNumber];
  }

  if (!gridLookup || !raw || typeof raw !== "object") {
    return undefined;
  }
  for (const key of Object.keys(raw as Record<string, unknown>)) {
    const match = /^[xy]axis(\d*)\./.exec(key);
    if (!match) {
      continue;
    }
    const cellIndex = (match[1] ? Number(match[1]) : 1) - 1;
    const subplotIndex = gridLookup.subplots.findIndex(
      (s) => gridCellIndex(s.row, s.col, gridLookup.cols) === cellIndex,
    );
    return subplotIndex === -1 ? undefined : subplotIndex;
  }
  return undefined;
}
