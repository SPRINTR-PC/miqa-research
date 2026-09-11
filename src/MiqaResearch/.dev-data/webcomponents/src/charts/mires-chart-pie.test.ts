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

const { buildPieTraces } = await import("./mires-chart-pie.js");
type PieChartData = Parameters<typeof buildPieTraces>[0];

describe("buildPieTraces", () => {
  it("builds a single plain-pie trace when config.hole is unset", () => {
    const data: PieChartData = {
      labels: ["A", "B", "C"],
      values: [4, 9, 2],
    };

    const traces = buildPieTraces(data);

    expect(traces).toHaveLength(1);
    expect(traces[0]).toMatchObject({
      type: "pie",
      labels: ["A", "B", "C"],
      values: [4, 9, 2],
      hole: 0,
      sort: true,
      textinfo: "label+percent",
    });
  });

  it("builds a donut trace when config.hole > 0", () => {
    const data: PieChartData = { labels: ["A", "B"], values: [1, 2] };

    const traces = buildPieTraces(data, { hole: 0.6 });

    expect(traces).toHaveLength(1);
    expect(traces[0]).toMatchObject({ type: "pie", hole: 0.6 });
  });

  it("respects config.sort = false", () => {
    const data: PieChartData = { labels: ["A", "B"], values: [1, 2] };

    const traces = buildPieTraces(data, { sort: false });

    expect(traces[0]).toMatchObject({ sort: false });
  });

  it("respects config.textinfo", () => {
    const data: PieChartData = { labels: ["A", "B"], values: [1, 2] };

    const traces = buildPieTraces(data, { textinfo: "value" });

    expect(traces[0]).toMatchObject({ textinfo: "value" });
  });

  it("never includes a per-slice color field — colors come from the categorical colorway", () => {
    const data: PieChartData = { labels: ["A", "B"], values: [1, 2] };

    const traces = buildPieTraces(data);

    expect(traces[0]?.marker).toBeUndefined();
    expect(traces[0]?.color).toBeUndefined();
    expect(traces[0]?.colors).toBeUndefined();
  });
});

describe("MiresChartPie", () => {
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

  it("renders a plain pie when config is absent", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({
        groupings: [{ name: "n", label: "N", data: { labels: ["A", "B"], values: [4, 9] } }],
      }),
    );

    const el = document.createElement("mires-chart-pie");
    el.setAttribute("data-url", "/fixture.json");
    document.body.appendChild(el);
    await waitForRenderCount(1);

    const [, traces] = reactMock.mock.calls[0] as [unknown, { hole: number; labels: string[] }[]];
    expect(traces[0]?.hole).toBe(0);
    expect(traces[0]?.labels).toEqual(["A", "B"]);
  });

  it("renders a donut when config.hole > 0", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({
        config: { hole: 0.5 },
        groupings: [{ name: "n", label: "N", data: { labels: ["A", "B"], values: [4, 9] } }],
      }),
    );

    const el = document.createElement("mires-chart-pie");
    el.setAttribute("data-url", "/fixture.json");
    document.body.appendChild(el);
    await waitForRenderCount(1);

    const [, traces] = reactMock.mock.calls[0] as [unknown, { hole: number }[]];
    expect(traces[0]?.hole).toBe(0.5);
  });

  it("respects config.sort and config.textinfo", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({
        config: { sort: false, textinfo: "value+percent" },
        groupings: [{ name: "n", label: "N", data: { labels: ["A", "B"], values: [4, 9] } }],
      }),
    );

    const el = document.createElement("mires-chart-pie");
    el.setAttribute("data-url", "/fixture.json");
    document.body.appendChild(el);
    await waitForRenderCount(1);

    const [, traces] = reactMock.mock.calls[0] as [unknown, { sort: boolean; textinfo: string }[]];
    expect(traces[0]?.sort).toBe(false);
    expect(traces[0]?.textinfo).toBe("value+percent");
  });

  it("never upgrades to a WebGL trace type — documented no-op for pie (§5)", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({
        groupings: [{ name: "n", label: "N", data: { labels: ["A", "B"], values: [4, 9] } }],
      }),
    );

    const el = document.createElement("mires-chart-pie");
    el.setAttribute("data-url", "/fixture.json");
    document.body.appendChild(el);
    await waitForRenderCount(1);

    const [, traces] = reactMock.mock.calls[0] as [unknown, { type: string }[]];
    expect(traces[0]?.type).toBe("pie");
  });
});
