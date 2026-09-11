import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { gridCellDomain } from "./chart-grid-utils.js";
import { registerChartCallback, unregisterChartCallback } from "./chart-callback-registry.js";

const { reactMock, resizeMock } = vi.hoisted(() => ({
  reactMock: vi.fn(),
  resizeMock: vi.fn(),
}));

vi.mock("plotly.js", () => ({
  default: { react: reactMock, Plots: { resize: resizeMock } },
  react: reactMock,
  Plots: { resize: resizeMock },
}));

const { buildChartGridTraces, MiresChartGrid } = await import("./mires-chart-grid.js");
type ChartGridData = Parameters<typeof buildChartGridTraces>[0];
type ChartGridConfig = Parameters<typeof buildChartGridTraces>[1];
type ChartGridPaletteColors = Parameters<typeof buildChartGridTraces>[2];
type MiresChartGridElement = InstanceType<typeof MiresChartGrid>;

const COLORS: ChartGridPaletteColors = {
  sequential: ["#fff", "#ccc", "#999", "#666", "#333", "#000"],
  diverging: ["#2a78d6", "#f0efec", "#e34948"],
  sankeyNodeDefault: "#9a9a94",
};

describe("buildChartGridTraces", () => {
  it("mixes an axis-based type (bar) with both non-axis types (pie, sankey), each keeping its own builder's shape", () => {
    const config: ChartGridConfig = {
      rows: 1,
      cols: 3,
      subplots: [
        { type: "bar", row: 0, col: 0 },
        { type: "pie", row: 0, col: 1 },
        { type: "sankey", row: 0, col: 2 },
      ],
    };
    const data: ChartGridData = {
      subplots: [
        { categories: ["A", "B"], series: [{ name: "S", values: [1, 2] }] },
        { labels: ["X", "Y"], values: [3, 4] },
        { nodes: [{ label: "A" }, { label: "B" }], links: [{ source: 0, target: 1, value: 1 }] },
      ],
    };

    const { traces } = buildChartGridTraces(data, config, COLORS);

    expect(traces).toHaveLength(3);
    expect(traces[0]).toMatchObject({ type: "bar", x: ["A", "B"], y: [1, 2] });
    expect(traces[1]).toMatchObject({ type: "pie", labels: ["X", "Y"] });
    expect(traces[2]).toMatchObject({ type: "sankey", node: { label: ["A", "B"] } });
  });

  it("positions non-axis subplots via the exact domain gridCellDomain computes for their row/col", () => {
    const config: ChartGridConfig = {
      rows: 1,
      cols: 2,
      subplots: [
        { type: "pie", row: 0, col: 0 },
        { type: "sankey", row: 0, col: 1 },
      ],
    };
    const data: ChartGridData = {
      subplots: [
        { labels: ["X"], values: [1] },
        { nodes: [{ label: "A" }, { label: "B" }], links: [{ source: 0, target: 1, value: 1 }] },
      ],
    };

    const { traces } = buildChartGridTraces(data, config, COLORS);

    expect(traces[0]?.domain).toEqual(gridCellDomain(0, 0, 1, 2));
    expect(traces[1]?.domain).toEqual(gridCellDomain(0, 1, 1, 2));
    expect(traces[0]?.xaxis).toBeUndefined();
    expect(traces[0]?.yaxis).toBeUndefined();
  });

  it("assigns axis suffixes by grid-cell position, unaffected by an axis-less subplot occupying an earlier cell", () => {
    const config: ChartGridConfig = {
      rows: 1,
      cols: 3,
      subplots: [
        { type: "pie", row: 0, col: 0 },
        { type: "bar", row: 0, col: 1 },
        { type: "bar", row: 0, col: 2 },
      ],
    };
    const data: ChartGridData = {
      subplots: [
        { labels: ["X"], values: [1] },
        { categories: ["A"], series: [{ name: "S", values: [1] }] },
        { categories: ["A"], series: [{ name: "S", values: [1] }] },
      ],
    };

    const { traces } = buildChartGridTraces(data, config, COLORS);

    // subplot 0 is axis-less (pie) — no axis fields at all.
    expect(traces[0]?.xaxis).toBeUndefined();
    // subplot 1 occupies grid cell (0,1) = cellIndex 1 -> suffix "2".
    expect(traces[1]).toMatchObject({ xaxis: "x2", yaxis: "y2" });
    // subplot 2 occupies grid cell (0,2) = cellIndex 2 -> suffix "3".
    expect(traces[2]).toMatchObject({ xaxis: "x3", yaxis: "y3" });
  });

  it("derives the axis suffix from the subplot's row/col grid cell, not its position in config.subplots", () => {
    const config: ChartGridConfig = {
      rows: 1,
      cols: 2,
      subplots: [
        // Listed out of grid-cell order: array index 0 sits in the right-hand cell (col 1),
        // array index 1 sits in the left-hand cell (col 0).
        { type: "bar", row: 0, col: 1 },
        { type: "bar", row: 0, col: 0 },
      ],
    };
    const data: ChartGridData = {
      subplots: [
        { categories: ["A"], series: [{ name: "Right", values: [1] }] },
        { categories: ["A"], series: [{ name: "Left", values: [2] }] },
      ],
    };

    const { traces } = buildChartGridTraces(data, config, COLORS);

    // The right-hand subplot (col 1 = cellIndex 1) gets the suffixed axis, even
    // though it's array index 0 — a naive index-based numbering would get this backwards.
    expect(traces[0]).toMatchObject({ name: "Right", xaxis: "x2", yaxis: "y2" });
    expect(traces[1]).toMatchObject({ name: "Left", xaxis: "x", yaxis: "y" });
  });

  it("leaves the first axis-based subplot's axis unsuffixed", () => {
    const config: ChartGridConfig = {
      rows: 1,
      cols: 1,
      subplots: [{ type: "bar", row: 0, col: 0 }],
    };
    const data: ChartGridData = { subplots: [{ categories: ["A"], series: [{ name: "S", values: [1] }] }] };

    const { traces } = buildChartGridTraces(data, config, COLORS);

    expect(traces[0]).toMatchObject({ xaxis: "x", yaxis: "y" });
  });

  it("tracks which subplot each trace belongs to, including a subplot producing multiple traces", () => {
    const config: ChartGridConfig = {
      rows: 1,
      cols: 2,
      subplots: [
        { type: "bar", row: 0, col: 0 },
        { type: "pie", row: 0, col: 1 },
      ],
    };
    const data: ChartGridData = {
      subplots: [
        {
          categories: ["A", "B"],
          series: [
            { name: "Site A", values: [1, 2] },
            { name: "Site B", values: [3, 4] },
          ],
        },
        { labels: ["X"], values: [1] },
      ],
    };

    const { traces, traceSubplotIndices } = buildChartGridTraces(data, config, COLORS);

    expect(traces).toHaveLength(3);
    expect(traceSubplotIndices).toEqual([0, 0, 1]);
  });

  it("warns and skips a subplot naming an unknown chart type, without breaking the rest of the grid", () => {
    const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => undefined);
    const config: ChartGridConfig = {
      rows: 1,
      cols: 2,
      subplots: [
        { type: "not-a-real-type", row: 0, col: 0 },
        { type: "bar", row: 0, col: 1 },
      ],
    };
    const data: ChartGridData = {
      subplots: [{}, { categories: ["A"], series: [{ name: "S", values: [1] }] }],
    };

    const { traces, traceSubplotIndices } = buildChartGridTraces(data, config, COLORS);

    expect(traces).toHaveLength(1);
    expect(traces[0]).toMatchObject({ type: "bar", xaxis: "x2", yaxis: "y2" });
    expect(traceSubplotIndices).toEqual([1]);
    expect(warnSpy).toHaveBeenCalledWith(expect.stringContaining("not-a-real-type"));

    warnSpy.mockRestore();
  });
});

describe("MiresChartGrid", () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    reactMock.mockReset();
    resizeMock.mockReset();
    fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    document.body.innerHTML = "";
    vi.unstubAllGlobals();
  });

  function jsonResponse(body: unknown): Response {
    return new Response(JSON.stringify(body), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  }

  function graphDivHandlers(): { on: ReturnType<typeof vi.fn>; handlers: Record<string, (ev: unknown) => void> } {
    const handlers: Record<string, (ev: unknown) => void> = {};
    const on = vi.fn((event: string, cb: (ev: unknown) => void) => {
      handlers[event] = cb;
    });
    return { on, handlers };
  }

  async function waitForRenderCount(min: number): Promise<void> {
    await vi.waitFor(() => {
      if (reactMock.mock.calls.length < min) {
        throw new Error(`expected at least ${min} render(s), got ${reactMock.mock.calls.length}`);
      }
    });
  }

  const twoSubplotResponse = (groupings: unknown[]): unknown => ({
    config: {
      rows: 1,
      cols: 2,
      subplots: [
        { type: "bar", row: 0, col: 0 },
        { type: "pie", row: 0, col: 1 },
      ],
      event_callbacks: { click: "grid-click-callback", zoom: "grid-zoom-callback" },
    },
    groupings,
  });

  afterEach(() => {
    unregisterChartCallback("grid-click-callback");
    unregisterChartCallback("grid-zoom-callback");
  });

  it("renders traces for every subplot from one combined dataUrl", async () => {
    reactMock.mockResolvedValue({ on: vi.fn() });
    fetchMock.mockResolvedValue(
      jsonResponse(
        twoSubplotResponse([
          {
            name: "n",
            label: "N",
            data: {
              subplots: [
                { categories: ["A"], series: [{ name: "S", values: [1] }] },
                { labels: ["X"], values: [1] },
              ],
            },
          },
        ]),
      ),
    );

    const el = document.createElement("mires-chart-grid") as MiresChartGridElement;
    el.setAttribute("data-url", "/fixture.json");
    document.body.appendChild(el);
    await waitForRenderCount(1);

    const [, traces] = reactMock.mock.calls[0] as [unknown, { type: string }[]];
    expect(traces.map((t) => t.type)).toEqual(["bar", "pie"]);
  });

  it("switches every subplot's data together on a Grouping change, with no refetch", async () => {
    reactMock.mockResolvedValue({ on: vi.fn() });
    fetchMock.mockResolvedValue(
      jsonResponse(
        twoSubplotResponse([
          {
            name: "g1",
            label: "Grouping 1",
            data: {
              subplots: [
                { categories: ["A"], series: [{ name: "S", values: [1] }] },
                { labels: ["X"], values: [1] },
              ],
            },
          },
          {
            name: "g2",
            label: "Grouping 2",
            data: {
              subplots: [
                { categories: ["A"], series: [{ name: "S", values: [99] }] },
                { labels: ["X"], values: [99] },
              ],
            },
          },
        ]),
      ),
    );

    const el = document.createElement("mires-chart-grid") as MiresChartGridElement;
    el.setAttribute("data-url", "/fixture.json");
    document.body.appendChild(el);
    await waitForRenderCount(1);
    expect(fetchMock).toHaveBeenCalledTimes(1);

    const select = el.renderRoot.querySelector("kp-select");
    expect(select).not.toBeNull();
    select?.dispatchEvent(new CustomEvent("change", { detail: { value: "1" } }));
    await waitForRenderCount(2);

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [, traces] = reactMock.mock.calls.at(-1) as [unknown, { y?: number[]; values?: number[] }[]];
    expect(traces[0]?.y).toEqual([99]);
    expect(traces[1]?.values).toEqual([99]);
  });

  it("attributes a click event to the specific subplot's chart type, not the grid as a whole", async () => {
    const { on, handlers } = graphDivHandlers();
    reactMock.mockResolvedValue({ on });
    fetchMock.mockResolvedValue(
      jsonResponse(
        twoSubplotResponse([
          {
            name: "n",
            label: "N",
            data: {
              subplots: [
                { categories: ["A"], series: [{ name: "S", values: [1] }] },
                { labels: ["X"], values: [1] },
              ],
            },
          },
        ]),
      ),
    );
    const callback = vi.fn();
    registerChartCallback("grid-click-callback", callback);

    const el = document.createElement("mires-chart-grid") as MiresChartGridElement;
    el.setAttribute("data-url", "/fixture.json");
    document.body.appendChild(el);
    await waitForRenderCount(1);

    // trace 0 = bar subplot, trace 1 = pie subplot.
    handlers.plotly_click?.({ points: [{ curveNumber: 1 }] });

    expect(callback).toHaveBeenCalledWith(
      expect.objectContaining({ chartType: "pie", event: "click", groupingName: "n" }),
    );
  });

  it("attributes a zoom event to the axis-based subplot that owns the relayouted axis", async () => {
    const { on, handlers } = graphDivHandlers();
    reactMock.mockResolvedValue({ on });
    fetchMock.mockResolvedValue(
      jsonResponse({
        config: {
          rows: 1,
          cols: 2,
          subplots: [
            { type: "pie", row: 0, col: 0 },
            { type: "bar", row: 0, col: 1 },
          ],
          event_callbacks: { zoom: "grid-zoom-callback" },
        },
        groupings: [
          {
            name: "n",
            label: "N",
            data: {
              subplots: [
                { labels: ["X"], values: [1] },
                { categories: ["A"], series: [{ name: "S", values: [1] }] },
              ],
            },
          },
        ],
      }),
    );
    const callback = vi.fn();
    registerChartCallback("grid-zoom-callback", callback);

    const el = document.createElement("mires-chart-grid") as MiresChartGridElement;
    el.setAttribute("data-url", "/fixture.json");
    document.body.appendChild(el);
    await waitForRenderCount(1);

    // subplot 0 (pie) is axis-less; subplot 1 (bar) is the 2nd entry -> "xaxis2".
    handlers.plotly_relayout?.({ "xaxis2.range[0]": 0, "xaxis2.range[1]": 10 });

    expect(callback).toHaveBeenCalledWith(expect.objectContaining({ chartType: "bar", event: "zoom" }));
  });
});
