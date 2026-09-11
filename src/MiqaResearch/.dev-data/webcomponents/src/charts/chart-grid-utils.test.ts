import { describe, expect, it } from "vitest";

import { gridCellDomain, gridCellIndex, resolveSubplotIndexFromEvent } from "./chart-grid-utils.js";

describe("gridCellIndex", () => {
  it("computes a row-major cell index from row/col and the grid's column count", () => {
    expect(gridCellIndex(0, 0, 3)).toBe(0);
    expect(gridCellIndex(0, 2, 3)).toBe(2);
    expect(gridCellIndex(1, 0, 3)).toBe(3);
    expect(gridCellIndex(2, 1, 3)).toBe(7);
  });
});

describe("gridCellDomain", () => {
  it("splits a 2x2 grid into four quadrants with row 0 at the top of the y domain", () => {
    expect(gridCellDomain(0, 0, 2, 2)).toEqual({ x: [0.02, 0.48], y: [0.52, 0.98] });
    expect(gridCellDomain(0, 1, 2, 2)).toEqual({ x: [0.52, 0.98], y: [0.52, 0.98] });
    expect(gridCellDomain(1, 0, 2, 2)).toEqual({ x: [0.02, 0.48], y: [0.02, 0.48] });
    expect(gridCellDomain(1, 1, 2, 2)).toEqual({ x: [0.52, 0.98], y: [0.02, 0.48] });
  });

  it("fills the full [0, 1] range per cell when the gutter is 0", () => {
    expect(gridCellDomain(0, 0, 2, 2, 0)).toEqual({ x: [0, 0.5], y: [0.5, 1] });
    expect(gridCellDomain(1, 1, 2, 2, 0)).toEqual({ x: [0.5, 1], y: [0, 0.5] });
  });

  it("returns the full domain for a 1x1 grid", () => {
    expect(gridCellDomain(0, 0, 1, 1, 0)).toEqual({ x: [0, 1], y: [0, 1] });
  });
});

describe("resolveSubplotIndexFromEvent", () => {
  const traceSubplotIndices = [0, 0, 1, 2];

  it("resolves a click event's curveNumber to its owning subplot index", () => {
    expect(resolveSubplotIndexFromEvent("click", { points: [{ curveNumber: 2 }] }, traceSubplotIndices)).toBe(1);
    expect(resolveSubplotIndexFromEvent("click", { points: [{ curveNumber: 0 }] }, traceSubplotIndices)).toBe(0);
    expect(resolveSubplotIndexFromEvent("click", { points: [{ curveNumber: 3 }] }, traceSubplotIndices)).toBe(2);
  });

  it("returns undefined for a click event with no points", () => {
    expect(resolveSubplotIndexFromEvent("click", { points: [] }, traceSubplotIndices)).toBeUndefined();
    expect(resolveSubplotIndexFromEvent("click", {}, traceSubplotIndices)).toBeUndefined();
  });

  // subplots[0] occupies grid cell (0,1) = cellIndex 1 -> axis "2"; subplots[1]
  // occupies (0,0) = cellIndex 0 -> the unsuffixed axis. Array order is
  // deliberately the reverse of grid-cell order, so these tests only pass if
  // the lookup is genuinely driven by row/col rather than array position.
  const gridLookup = {
    cols: 2,
    subplots: [
      { row: 0, col: 1 },
      { row: 0, col: 0 },
    ],
  };

  it("resolves a zoom event's unsuffixed axis key to the subplot occupying grid cell 0", () => {
    expect(
      resolveSubplotIndexFromEvent("zoom", { "xaxis.range[0]": 0, "xaxis.range[1]": 10 }, [], gridLookup),
    ).toBe(1);
  });

  it("resolves a zoom event's suffixed axis key by the subplot's row/col cell position, not its array index", () => {
    expect(resolveSubplotIndexFromEvent("zoom", { "xaxis2.range[0]": 0 }, [], gridLookup)).toBe(0);
    expect(resolveSubplotIndexFromEvent("zoom", { "yaxis2.autorange": true }, [], gridLookup)).toBe(0);
  });

  it("returns undefined for a zoom event whose axis matches no subplot's grid cell", () => {
    expect(resolveSubplotIndexFromEvent("zoom", { "xaxis3.range[0]": 0 }, [], gridLookup)).toBeUndefined();
  });

  it("returns undefined for a zoom event carrying no axis-scoped key", () => {
    expect(resolveSubplotIndexFromEvent("zoom", { autosize: true }, [], gridLookup)).toBeUndefined();
  });

  it("returns undefined for a zoom event when no gridLookup is supplied", () => {
    expect(resolveSubplotIndexFromEvent("zoom", { "xaxis.range[0]": 0 }, [])).toBeUndefined();
  });
});
