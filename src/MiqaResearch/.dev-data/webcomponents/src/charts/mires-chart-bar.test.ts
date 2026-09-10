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

const { buildBarTraces } = await import("./mires-chart-bar.js");
type BarChartData = Parameters<typeof buildBarTraces>[0];

describe("buildBarTraces", () => {
  it("builds a single trace for a single-series bar chart", () => {
    const data: BarChartData = {
      categories: ["A", "B", "C"],
      series: [{ name: "Consents", values: [4, 9, 2] }],
    };

    const traces = buildBarTraces(data);

    expect(traces).toHaveLength(1);
    expect(traces[0]).toMatchObject({
      type: "bar",
      orientation: "v",
      name: "Consents",
      x: ["A", "B", "C"],
      y: [4, 9, 2],
    });
  });

  it("builds one trace per series for a grouped multi-series bar chart", () => {
    const data: BarChartData = {
      categories: ["A", "B"],
      series: [
        { name: "Site A", values: [1, 2] },
        { name: "Site B", values: [3, 4] },
      ],
    };

    const traces = buildBarTraces(data, { barMode: "group" });

    expect(traces).toHaveLength(2);
    expect(traces[0]).toMatchObject({ name: "Site A", x: ["A", "B"], y: [1, 2] });
    expect(traces[1]).toMatchObject({ name: "Site B", x: ["A", "B"], y: [3, 4] });
  });

  it("builds one trace per series for a stacked multi-series bar chart", () => {
    const data: BarChartData = {
      categories: ["A", "B"],
      series: [
        { name: "Site A", values: [1, 2] },
        { name: "Site B", values: [3, 4] },
      ],
    };

    const traces = buildBarTraces(data, { barMode: "stack" });

    expect(traces).toHaveLength(2);
    expect(traces[0]).toMatchObject({ name: "Site A", x: ["A", "B"], y: [1, 2] });
    expect(traces[1]).toMatchObject({ name: "Site B", x: ["A", "B"], y: [3, 4] });
  });

  it("swaps x/y and sets orientation for horizontal orientation", () => {
    const data: BarChartData = {
      categories: ["A", "B", "C"],
      series: [{ name: "Consents", values: [4, 9, 2] }],
    };

    const traces = buildBarTraces(data, { orientation: "h" });

    expect(traces[0]).toMatchObject({
      type: "bar",
      orientation: "h",
      x: [4, 9, 2],
      y: ["A", "B", "C"],
    });
  });
});

describe("MiresChartBar", () => {
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

  it("defaults layout.barmode to group and orientation to v when config is absent", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({
        groupings: [
          { name: "n", label: "N", data: { categories: ["A"], series: [{ name: "S", values: [1] }] } },
        ],
      }),
    );

    const el = document.createElement("mires-chart-bar");
    el.setAttribute("data-url", "/fixture.json");
    document.body.appendChild(el);
    await waitForRenderCount(1);

    const [, traces, layout] = reactMock.mock.calls[0] as [unknown, { orientation: string }[], { barmode: string }];
    expect(layout.barmode).toBe("group");
    expect(traces[0]?.orientation).toBe("v");
  });

  it("respects config.barMode and config.orientation via extraLayout()", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({
        config: { bar_mode: "stack", orientation: "h" },
        groupings: [
          { name: "n", label: "N", data: { categories: ["A"], series: [{ name: "S", values: [1] }] } },
        ],
      }),
    );

    const el = document.createElement("mires-chart-bar");
    el.setAttribute("data-url", "/fixture.json");
    document.body.appendChild(el);
    await waitForRenderCount(1);

    const [, traces, layout] = reactMock.mock.calls[0] as [unknown, { orientation: string }[], { barmode: string }];
    expect(layout.barmode).toBe("stack");
    expect(traces[0]?.orientation).toBe("h");
  });

  it("never upgrades to a WebGL trace type — documented no-op for bar (§5)", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({
        groupings: [
          {
            name: "n",
            label: "N",
            data: { categories: ["A"], series: [{ name: "S", values: [1] }] },
          },
        ],
      }),
    );

    const el = document.createElement("mires-chart-bar");
    el.setAttribute("data-url", "/fixture.json");
    document.body.appendChild(el);
    await waitForRenderCount(1);

    const [, traces] = reactMock.mock.calls[0] as [unknown, { type: string }[]];
    expect(traces[0]?.type).toBe("bar");
  });
});
