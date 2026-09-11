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

const { buildHeatmapTraces } = await import("./mires-chart-heatmap.js");
type HeatmapChartData = Parameters<typeof buildHeatmapTraces>[0];
type HeatmapChartConfig = Parameters<typeof buildHeatmapTraces>[1];
type HeatmapChartColors = Parameters<typeof buildHeatmapTraces>[2];

const COLORS: HeatmapChartColors = {
  sequential: ["#fff", "#ccc", "#999", "#666", "#333", "#000"],
  diverging: ["#2a78d6", "#f0efec", "#e34948"],
};

describe("buildHeatmapTraces", () => {
  it("builds a single heatmap trace carrying the z matrix", () => {
    const data: HeatmapChartData = { z: [[1, 2], [3, 4]] };

    const traces = buildHeatmapTraces(data, undefined, COLORS);

    expect(traces).toHaveLength(1);
    expect(traces[0]).toMatchObject({ type: "heatmap", z: [[1, 2], [3, 4]] });
  });

  it("leaves x/y undefined when omitted, defaulting to indices", () => {
    const data: HeatmapChartData = { z: [[1, 2]] };

    const traces = buildHeatmapTraces(data, undefined, COLORS);

    expect(traces[0]?.x).toBeUndefined();
    expect(traces[0]?.y).toBeUndefined();
  });

  it("passes through explicit x/y axis labels", () => {
    const data: HeatmapChartData = { z: [[1, 2]], x: ["a", "b"], y: ["row1"] };

    const traces = buildHeatmapTraces(data, undefined, COLORS);

    expect(traces[0]).toMatchObject({ x: ["a", "b"], y: ["row1"] });
  });

  it("defaults to the sequential colorscale, evenly stepped across the ramp, with no zmid", () => {
    const data: HeatmapChartData = { z: [[1]] };

    const traces = buildHeatmapTraces(data, undefined, COLORS);

    expect(traces[0]?.colorscale).toEqual([
      [0, "#fff"],
      [0.2, "#ccc"],
      [0.4, "#999"],
      [0.6, "#666"],
      [0.8, "#333"],
      [1, "#000"],
    ]);
    expect(traces[0]?.zmid).toBeUndefined();
  });

  it("builds a 3-stop diverging colorscale and defaults zMid to 0", () => {
    const data: HeatmapChartData = { z: [[-1, 1]] };
    const config: HeatmapChartConfig = { colorScale: "diverging" };

    const traces = buildHeatmapTraces(data, config, COLORS);

    expect(traces[0]?.colorscale).toEqual([
      [0, "#2a78d6"],
      [0.5, "#f0efec"],
      [1, "#e34948"],
    ]);
    expect(traces[0]?.zmid).toBe(0);
  });

  it("respects an explicit config.zMid for the diverging scale", () => {
    const data: HeatmapChartData = { z: [[-1, 1]] };
    const config: HeatmapChartConfig = { colorScale: "diverging", zMid: 50 };

    const traces = buildHeatmapTraces(data, config, COLORS);

    expect(traces[0]?.zmid).toBe(50);
  });
});

describe("MiresChartHeatmap", () => {
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

  it("never upgrades to a WebGL trace type — documented no-op for heatmap (§5/§7.6)", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ groupings: [{ name: "n", label: "N", data: { z: [[1, 2]] } }] }),
    );

    const el = document.createElement("mires-chart-heatmap");
    el.setAttribute("data-url", "/fixture.json");
    document.body.appendChild(el);
    await waitForRenderCount(1);

    const [, traces] = reactMock.mock.calls[0] as [unknown, { type: string }[]];
    expect(traces[0]?.type).toBe("heatmap");
  });

  it("threads config.color_scale and config.z_mid through to the rendered trace", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({
        config: { color_scale: "diverging", z_mid: 10 },
        groupings: [{ name: "n", label: "N", data: { z: [[-1, 1]] } }],
      }),
    );

    const el = document.createElement("mires-chart-heatmap");
    el.setAttribute("data-url", "/fixture.json");
    document.body.appendChild(el);
    await waitForRenderCount(1);

    const [, traces] = reactMock.mock.calls[0] as [unknown, { zmid: number; colorscale: unknown[] }[]];
    expect(traces[0]?.zmid).toBe(10);
    expect(traces[0]?.colorscale).toHaveLength(3);
  });
});
