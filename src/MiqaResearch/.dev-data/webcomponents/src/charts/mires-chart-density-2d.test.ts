import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { reactMock, resizeMock } = vi.hoisted(() => ({
  reactMock: vi.fn(),
  resizeMock: vi.fn(),
}));

vi.mock("plotly.js", () => ({
  default: { react: reactMock, Plots: { resize: resizeMock } },
  react: reactMock,
  Plots: { resize: resizeMock },
}));

const { buildDensity2DTraces } = await import("./mires-chart-density-2d.js");
type Density2DChartData = Parameters<typeof buildDensity2DTraces>[0];
type Density2DChartColors = Parameters<typeof buildDensity2DTraces>[2];

const COLORS: Density2DChartColors = {
  sequential: ["#fff", "#ccc", "#999", "#666", "#333", "#000"],
};

describe("buildDensity2DTraces", () => {
  it("defaults to a single histogram2d trace for a single series with no config", () => {
    const data: Density2DChartData = {
      series: [{ name: "All", x: [1, 2, 3], y: [4, 5, 6] }],
    };

    const traces = buildDensity2DTraces(data, undefined, COLORS);

    expect(traces).toHaveLength(1);
    expect(traces[0]).toMatchObject({
      type: "histogram2d",
      name: "All",
      x: [1, 2, 3],
      y: [4, 5, 6],
    });
    expect(traces[0]?.nbinsx).toBeUndefined();
    expect(traces[0]?.xbins).toBeUndefined();
  });

  it("builds histogram2dcontour traces when config.style is contour", () => {
    const data: Density2DChartData = {
      series: [{ name: "All", x: [1, 2], y: [3, 4] }],
    };

    const traces = buildDensity2DTraces(data, { style: "contour" }, COLORS);

    expect(traces[0]).toMatchObject({ type: "histogram2dcontour" });
  });

  it("builds one trace per series for a multi-series overlay", () => {
    const data: Density2DChartData = {
      series: [
        { name: "Site A", x: [1, 2], y: [1, 2] },
        { name: "Site B", x: [3, 4], y: [3, 4] },
      ],
    };

    const traces = buildDensity2DTraces(data, undefined, COLORS);

    expect(traces).toHaveLength(2);
    expect(traces[0]).toMatchObject({ name: "Site A" });
    expect(traces[1]).toMatchObject({ name: "Site B" });
  });

  it("applies a chart-wide config.densityBins default to every series", () => {
    const data: Density2DChartData = {
      series: [
        { name: "Site A", x: [1, 2], y: [1, 2] },
        { name: "Site B", x: [3, 4], y: [3, 4] },
      ],
    };

    const traces = buildDensity2DTraces(
      data,
      { densityBins: { nbinsx: 10, nbinsy: 20, xbins: { start: 0, end: 100, size: 10 } } },
      COLORS,
    );

    expect(traces[0]).toMatchObject({ nbinsx: 10, nbinsy: 20, xbins: { start: 0, end: 100, size: 10 } });
    expect(traces[1]).toMatchObject({ nbinsx: 10, nbinsy: 20, xbins: { start: 0, end: 100, size: 10 } });
  });

  it("lets a per-series bins override the chart-wide default", () => {
    const data: Density2DChartData = {
      series: [
        { name: "Site A", x: [1, 2], y: [1, 2], bins: { nbinsx: 5 } },
        { name: "Site B", x: [3, 4], y: [3, 4] },
      ],
    };

    const traces = buildDensity2DTraces(data, { densityBins: { nbinsx: 10 } }, COLORS);

    expect(traces[0]).toMatchObject({ nbinsx: 5 });
    expect(traces[1]).toMatchObject({ nbinsx: 10 });
  });

  it("always uses the sequential ramp, evenly stepped across the ramp — no diverging option for this type", () => {
    const data: Density2DChartData = { series: [{ name: "All", x: [1], y: [1] }] };

    const traces = buildDensity2DTraces(data, undefined, COLORS);

    expect(traces[0]?.colorscale).toEqual([
      [0, "#fff"],
      [0.2, "#ccc"],
      [0.4, "#999"],
      [0.6, "#666"],
      [0.8, "#333"],
      [1, "#000"],
    ]);
  });
});

describe("MiresChartDensity2D", () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    reactMock.mockReset();
    reactMock.mockResolvedValue({ on: vi.fn() });
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

  async function waitForRenderCount(min: number): Promise<void> {
    await vi.waitFor(() => {
      if (reactMock.mock.calls.length < min) {
        throw new Error(`expected at least ${min} render(s), got ${reactMock.mock.calls.length}`);
      }
    });
  }

  it("respects config.style = contour", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({
        config: { style: "contour" },
        groupings: [
          { name: "n", label: "N", data: { series: [{ name: "All", x: [1, 2], y: [3, 4] }] } },
        ],
      }),
    );

    const el = document.createElement("mires-chart-density-2d");
    el.setAttribute("data-url", "/fixture.json");
    document.body.appendChild(el);
    await waitForRenderCount(1);

    const [, traces] = reactMock.mock.calls[0] as [unknown, { type: string }[]];
    expect(traces[0]?.type).toBe("histogram2dcontour");
  });

  it("renders one trace per series for a multi-series overlay", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({
        groupings: [
          {
            name: "n",
            label: "N",
            data: {
              series: [
                { name: "Site A", x: [1, 2], y: [1, 2] },
                { name: "Site B", x: [3, 4], y: [3, 4] },
              ],
            },
          },
        ],
      }),
    );

    const el = document.createElement("mires-chart-density-2d");
    el.setAttribute("data-url", "/fixture.json");
    document.body.appendChild(el);
    await waitForRenderCount(1);

    const [, traces] = reactMock.mock.calls[0] as [unknown, { name: string }[]];
    expect(traces).toHaveLength(2);
    expect(traces.map((t) => t.name)).toEqual(["Site A", "Site B"]);
  });

  it("respects a chart-wide config.densityBins default", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({
        config: { density_bins: { nbinsx: 20, nbinsy: 20 } },
        groupings: [
          { name: "n", label: "N", data: { series: [{ name: "All", x: [1, 2], y: [3, 4] }] } },
        ],
      }),
    );

    const el = document.createElement("mires-chart-density-2d");
    el.setAttribute("data-url", "/fixture.json");
    document.body.appendChild(el);
    await waitForRenderCount(1);

    const [, traces] = reactMock.mock.calls[0] as [unknown, { nbinsx: number; nbinsy: number }[]];
    expect(traces[0]?.nbinsx).toBe(20);
    expect(traces[0]?.nbinsy).toBe(20);
  });

  it("never upgrades to a WebGL trace type — documented no-op for 2D density (§5/§7.7)", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({
        groupings: [
          { name: "n", label: "N", data: { series: [{ name: "All", x: [1, 2], y: [3, 4] }] } },
        ],
      }),
    );

    const el = document.createElement("mires-chart-density-2d");
    el.setAttribute("data-url", "/fixture.json");
    document.body.appendChild(el);
    await waitForRenderCount(1);

    const [, traces] = reactMock.mock.calls[0] as [unknown, { type: string }[]];
    expect(traces[0]?.type).toBe("histogram2d");
  });
});
