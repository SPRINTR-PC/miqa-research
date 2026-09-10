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

const { buildBoxTraces } = await import("./mires-chart-box.js");
type BoxChartData = Parameters<typeof buildBoxTraces>[0];

describe("buildBoxTraces", () => {
  it("builds a single trace for a flat list of named boxes with raw values", () => {
    const data: BoxChartData = {
      boxes: [
        { name: "A", values: [1, 2, 3] },
        { name: "B", values: [4, 5] },
      ],
    };

    const traces = buildBoxTraces(data);

    expect(traces).toHaveLength(1);
    expect(traces[0]).toMatchObject({
      type: "box",
      name: undefined,
      orientation: "v",
      quartilemethod: "linear",
      x: ["A", "A", "A", "B", "B"],
      y: [1, 2, 3, 4, 5],
    });
  });

  it("builds one trace per group for a grouped multi-dimension case (boxmode: group)", () => {
    const data: BoxChartData = {
      boxes: [
        { name: "Q1", group: "Site A", values: [1, 2] },
        { name: "Q2", group: "Site A", values: [3, 4] },
        { name: "Q1", group: "Site B", values: [5, 6] },
        { name: "Q2", group: "Site B", values: [7, 8] },
      ],
    };

    const traces = buildBoxTraces(data);

    expect(traces).toHaveLength(2);
    expect(traces[0]).toMatchObject({ name: "Site A", x: ["Q1", "Q1", "Q2", "Q2"], y: [1, 2, 3, 4] });
    expect(traces[1]).toMatchObject({ name: "Site B", x: ["Q1", "Q1", "Q2", "Q2"], y: [5, 6, 7, 8] });
  });

  it("builds a trace from precomputed stats instead of raw values", () => {
    const data: BoxChartData = {
      boxes: [
        { name: "A", stats: { q1: 1, median: 2, q3: 3, lowerFence: 0, upperFence: 4 } },
        { name: "B", stats: { q1: 5, median: 6, q3: 7 } },
      ],
    };

    const traces = buildBoxTraces(data);

    expect(traces).toHaveLength(1);
    expect(traces[0]).toMatchObject({
      type: "box",
      x: ["A", "B"],
      q1: [1, 5],
      median: [2, 6],
      q3: [3, 7],
      lowerfence: [0, undefined],
      upperfence: [4, undefined],
    });
    expect(traces[0]?.quartilemethod).toBeUndefined();
    expect(traces[0]?.y).toBeUndefined();
  });

  it("respects config.quartileMethod for raw-values boxes", () => {
    const data: BoxChartData = { boxes: [{ name: "A", values: [1, 2, 3] }] };

    const traces = buildBoxTraces(data, { quartileMethod: "exclusive" });

    expect(traces[0]).toMatchObject({ quartilemethod: "exclusive" });
  });

  it("respects config.orientation by swapping x/y for raw-values boxes", () => {
    const data: BoxChartData = { boxes: [{ name: "A", values: [1, 2] }] };

    const traces = buildBoxTraces(data, { orientation: "h" });

    expect(traces[0]).toMatchObject({ orientation: "h", x: [1, 2], y: ["A", "A"] });
  });

  it("respects config.orientation for stats-based boxes", () => {
    const data: BoxChartData = { boxes: [{ name: "A", stats: { q1: 1, median: 2, q3: 3 } }] };

    const traces = buildBoxTraces(data, { orientation: "h" });

    expect(traces[0]).toMatchObject({ orientation: "h", y: ["A"], q1: [1], median: [2], q3: [3] });
    expect(traces[0]?.x).toBeUndefined();
  });
});

describe("MiresChartBox", () => {
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

  it("sets layout.boxmode to group and defaults orientation to v when config is absent", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({
        groupings: [{ name: "n", label: "N", data: { boxes: [{ name: "A", values: [1, 2] }] } }],
      }),
    );

    const el = document.createElement("mires-chart-box");
    el.setAttribute("data-url", "/fixture.json");
    document.body.appendChild(el);
    await waitForRenderCount(1);

    const [, traces, layout] = reactMock.mock.calls[0] as [
      unknown,
      { orientation: string }[],
      { boxmode: string },
    ];
    expect(layout.boxmode).toBe("group");
    expect(traces[0]?.orientation).toBe("v");
  });

  it("respects config.quartile_method and config.orientation", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({
        config: { quartile_method: "inclusive", orientation: "h" },
        groupings: [{ name: "n", label: "N", data: { boxes: [{ name: "A", values: [1, 2] }] } }],
      }),
    );

    const el = document.createElement("mires-chart-box");
    el.setAttribute("data-url", "/fixture.json");
    document.body.appendChild(el);
    await waitForRenderCount(1);

    const [, traces] = reactMock.mock.calls[0] as [
      unknown,
      { orientation: string; quartilemethod: string }[],
    ];
    expect(traces[0]?.orientation).toBe("h");
    expect(traces[0]?.quartilemethod).toBe("inclusive");
  });

  it("never upgrades to a WebGL trace type — documented no-op for box (§5)", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({
        groupings: [{ name: "n", label: "N", data: { boxes: [{ name: "A", values: [1, 2] }] } }],
      }),
    );

    const el = document.createElement("mires-chart-box");
    el.setAttribute("data-url", "/fixture.json");
    document.body.appendChild(el);
    await waitForRenderCount(1);

    const [, traces] = reactMock.mock.calls[0] as [unknown, { type: string }[]];
    expect(traces[0]?.type).toBe("box");
  });
});
