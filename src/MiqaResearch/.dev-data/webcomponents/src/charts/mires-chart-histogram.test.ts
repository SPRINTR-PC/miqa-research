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

const { buildHistogramTraces } = await import("./mires-chart-histogram.js");
type HistogramChartData = Parameters<typeof buildHistogramTraces>[0];

describe("buildHistogramTraces", () => {
  it("builds a single trace for a single series with automatic (client-computed) binning", () => {
    const data: HistogramChartData = {
      series: [{ name: "Ages", values: [1, 2, 2, 3, 3, 3] }],
    };

    const traces = buildHistogramTraces(data);

    expect(traces).toHaveLength(1);
    expect(traces[0]).toMatchObject({
      type: "histogram",
      name: "Ages",
      orientation: "v",
      histnorm: "",
      x: [1, 2, 2, 3, 3, 3],
    });
    expect(traces[0]?.nbinsx).toBeUndefined();
    expect(traces[0]?.xbins).toBeUndefined();
  });

  it("applies a chart-wide config.histogramBins default to every series", () => {
    const data: HistogramChartData = {
      series: [
        { name: "Ages", values: [1, 2, 3] },
        { name: "Weights", values: [10, 20, 30] },
      ],
    };

    const traces = buildHistogramTraces(data, { histogramBins: { nbinsx: 10, start: 0, end: 100, size: 10 } });

    expect(traces[0]).toMatchObject({ nbinsx: 10, xbins: { start: 0, end: 100, size: 10 } });
    expect(traces[1]).toMatchObject({ nbinsx: 10, xbins: { start: 0, end: 100, size: 10 } });
  });

  it("lets a per-series bins override the chart-wide default", () => {
    const data: HistogramChartData = {
      series: [
        { name: "Ages", values: [1, 2, 3], bins: { nbinsx: 5 } },
        { name: "Weights", values: [10, 20, 30] },
      ],
    };

    const traces = buildHistogramTraces(data, { histogramBins: { nbinsx: 10 } });

    expect(traces[0]).toMatchObject({ nbinsx: 5 });
    expect(traces[1]).toMatchObject({ nbinsx: 10 });
  });

  it("swaps to y-values and nbinsy/ybins for horizontal orientation", () => {
    const data: HistogramChartData = {
      series: [{ name: "Ages", values: [1, 2, 3], bins: { nbinsx: 5, start: 0, end: 10, size: 1 } }],
    };

    const traces = buildHistogramTraces(data, { orientation: "h" });

    expect(traces[0]).toMatchObject({
      orientation: "h",
      y: [1, 2, 3],
      nbinsy: 5,
      ybins: { start: 0, end: 10, size: 1 },
    });
    expect(traces[0]?.x).toBeUndefined();
    expect(traces[0]?.nbinsx).toBeUndefined();
  });

  it("respects config.histnorm", () => {
    const data: HistogramChartData = { series: [{ name: "Ages", values: [1, 2, 3] }] };

    const traces = buildHistogramTraces(data, { histnorm: "percent" });

    expect(traces[0]).toMatchObject({ histnorm: "percent" });
  });
});

describe("MiresChartHistogram", () => {
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

  it("renders with automatic binning and orientation v when config is absent", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({
        groupings: [
          { name: "n", label: "N", data: { series: [{ name: "Ages", values: [1, 2, 3] }] } },
        ],
      }),
    );

    const el = document.createElement("mires-chart-histogram");
    el.setAttribute("data-url", "/fixture.json");
    document.body.appendChild(el);
    await waitForRenderCount(1);

    const [, traces] = reactMock.mock.calls[0] as [unknown, { orientation: string; x: number[] }[]];
    expect(traces[0]?.orientation).toBe("v");
    expect(traces[0]?.x).toEqual([1, 2, 3]);
  });

  it("respects a chart-wide config.histogramBins default", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({
        config: { histogram_bins: { nbinsx: 20 } },
        groupings: [
          { name: "n", label: "N", data: { series: [{ name: "Ages", values: [1, 2, 3] }] } },
        ],
      }),
    );

    const el = document.createElement("mires-chart-histogram");
    el.setAttribute("data-url", "/fixture.json");
    document.body.appendChild(el);
    await waitForRenderCount(1);

    const [, traces] = reactMock.mock.calls[0] as [unknown, { nbinsx: number }[]];
    expect(traces[0]?.nbinsx).toBe(20);
  });

  it("respects a per-series bins override over the chart-wide default", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({
        config: { histogram_bins: { nbinsx: 20 } },
        groupings: [
          {
            name: "n",
            label: "N",
            data: { series: [{ name: "Ages", values: [1, 2, 3], bins: { nbinsx: 5 } }] },
          },
        ],
      }),
    );

    const el = document.createElement("mires-chart-histogram");
    el.setAttribute("data-url", "/fixture.json");
    document.body.appendChild(el);
    await waitForRenderCount(1);

    const [, traces] = reactMock.mock.calls[0] as [unknown, { nbinsx: number }[]];
    expect(traces[0]?.nbinsx).toBe(5);
  });

  it("respects config.orientation = h", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({
        config: { orientation: "h" },
        groupings: [
          { name: "n", label: "N", data: { series: [{ name: "Ages", values: [1, 2, 3] }] } },
        ],
      }),
    );

    const el = document.createElement("mires-chart-histogram");
    el.setAttribute("data-url", "/fixture.json");
    document.body.appendChild(el);
    await waitForRenderCount(1);

    const [, traces] = reactMock.mock.calls[0] as [unknown, { orientation: string; y: number[] }[]];
    expect(traces[0]?.orientation).toBe("h");
    expect(traces[0]?.y).toEqual([1, 2, 3]);
  });

  it("respects config.histnorm", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({
        config: { histnorm: "probability" },
        groupings: [
          { name: "n", label: "N", data: { series: [{ name: "Ages", values: [1, 2, 3] }] } },
        ],
      }),
    );

    const el = document.createElement("mires-chart-histogram");
    el.setAttribute("data-url", "/fixture.json");
    document.body.appendChild(el);
    await waitForRenderCount(1);

    const [, traces] = reactMock.mock.calls[0] as [unknown, { histnorm: string }[]];
    expect(traces[0]?.histnorm).toBe("probability");
  });

  it("never upgrades to a WebGL trace type — documented no-op for histogram (§5)", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({
        groupings: [
          { name: "n", label: "N", data: { series: [{ name: "Ages", values: [1, 2, 3] }] } },
        ],
      }),
    );

    const el = document.createElement("mires-chart-histogram");
    el.setAttribute("data-url", "/fixture.json");
    document.body.appendChild(el);
    await waitForRenderCount(1);

    const [, traces] = reactMock.mock.calls[0] as [unknown, { type: string }[]];
    expect(traces[0]?.type).toBe("histogram");
  });
});
