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

const { buildSankeyTraces } = await import("./mires-chart-sankey.js");
type SankeyChartData = Parameters<typeof buildSankeyTraces>[0];
type SankeyChartConfig = Parameters<typeof buildSankeyTraces>[1];

const DEFAULT_NODE_COLOR = "#9a9a94";

describe("buildSankeyTraces", () => {
  const fixture: SankeyChartData = {
    nodes: [{ label: "A" }, { label: "B" }, { label: "C" }],
    links: [
      { source: 0, target: 1, value: 4 },
      { source: 1, target: 2, value: 2 },
    ],
  };

  it("builds a single sankey trace carrying node labels and link source/target/value", () => {
    const traces = buildSankeyTraces(fixture, undefined, DEFAULT_NODE_COLOR);

    expect(traces).toHaveLength(1);
    expect(traces[0]).toMatchObject({
      type: "sankey",
      node: { label: ["A", "B", "C"] },
      link: {
        source: [0, 1],
        target: [1, 2],
        value: [4, 2],
      },
    });
  });

  it("defaults every node to the neutral color when no override is given", () => {
    const traces = buildSankeyTraces(fixture, undefined, DEFAULT_NODE_COLOR);

    const node = traces[0]?.node as { color: string[] };
    expect(node.color).toEqual([DEFAULT_NODE_COLOR, DEFAULT_NODE_COLOR, DEFAULT_NODE_COLOR]);
  });

  it("defaults every link to a translucent tint of its source node's (default) color", () => {
    const traces = buildSankeyTraces(fixture, undefined, DEFAULT_NODE_COLOR);

    const link = traces[0]?.link as { color: string[] };
    expect(link.color).toEqual([
      "rgba(154, 154, 148, 0.4)",
      "rgba(154, 154, 148, 0.4)",
    ]);
  });

  it("respects explicit per-node color overrides", () => {
    const data: SankeyChartData = {
      nodes: [{ label: "A", color: "#2a78d6" }, { label: "B" }],
      links: [{ source: 0, target: 1, value: 1 }],
    };

    const traces = buildSankeyTraces(data, undefined, DEFAULT_NODE_COLOR);

    const node = traces[0]?.node as { color: string[] };
    expect(node.color).toEqual(["#2a78d6", DEFAULT_NODE_COLOR]);
  });

  it("tints an overridden node's outgoing link when the link itself has no override", () => {
    const data: SankeyChartData = {
      nodes: [{ label: "A", color: "#2a78d6" }, { label: "B" }],
      links: [{ source: 0, target: 1, value: 1 }],
    };

    const traces = buildSankeyTraces(data, undefined, DEFAULT_NODE_COLOR);

    const link = traces[0]?.link as { color: string[] };
    expect(link.color).toEqual(["rgba(42, 120, 214, 0.4)"]);
  });

  it("respects an explicit per-link color override over the source-tint default", () => {
    const data: SankeyChartData = {
      nodes: [{ label: "A" }, { label: "B" }],
      links: [{ source: 0, target: 1, value: 1, color: "#e34948" }],
    };

    const traces = buildSankeyTraces(data, undefined, DEFAULT_NODE_COLOR);

    const link = traces[0]?.link as { color: string[] };
    expect(link.color).toEqual(["#e34948"]);
  });

  it("defaults orientation to 'h' and arrangement to 'snap'", () => {
    const traces = buildSankeyTraces(fixture, undefined, DEFAULT_NODE_COLOR);

    expect(traces[0]).toMatchObject({ orientation: "h", arrangement: "snap" });
  });

  it("respects config.orientation", () => {
    const config: SankeyChartConfig = { orientation: "v" };

    const traces = buildSankeyTraces(fixture, config, DEFAULT_NODE_COLOR);

    expect(traces[0]).toMatchObject({ orientation: "v" });
  });

  it("respects config.arrangement", () => {
    const config: SankeyChartConfig = { arrangement: "freeform" };

    const traces = buildSankeyTraces(fixture, config, DEFAULT_NODE_COLOR);

    expect(traces[0]).toMatchObject({ arrangement: "freeform" });
  });
});

describe("MiresChartSankey", () => {
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

  it("renders a sankey trace from a nodes/links fixture", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({
        groupings: [
          {
            name: "n",
            label: "N",
            data: {
              nodes: [{ label: "A" }, { label: "B" }],
              links: [{ source: 0, target: 1, value: 5 }],
            },
          },
        ],
      }),
    );

    const el = document.createElement("mires-chart-sankey");
    el.setAttribute("data-url", "/fixture.json");
    document.body.appendChild(el);
    await waitForRenderCount(1);

    const [, traces] = reactMock.mock.calls[0] as [
      unknown,
      { type: string; node: { label: string[] } }[],
    ];
    expect(traces[0]?.type).toBe("sankey");
    expect(traces[0]?.node.label).toEqual(["A", "B"]);
  });

  it("threads config.orientation and config.arrangement through to the rendered trace", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({
        config: { orientation: "v", arrangement: "perpendicular" },
        groupings: [
          {
            name: "n",
            label: "N",
            data: {
              nodes: [{ label: "A" }, { label: "B" }],
              links: [{ source: 0, target: 1, value: 5 }],
            },
          },
        ],
      }),
    );

    const el = document.createElement("mires-chart-sankey");
    el.setAttribute("data-url", "/fixture.json");
    document.body.appendChild(el);
    await waitForRenderCount(1);

    const [, traces] = reactMock.mock.calls[0] as [
      unknown,
      { orientation: string; arrangement: string }[],
    ];
    expect(traces[0]?.orientation).toBe("v");
    expect(traces[0]?.arrangement).toBe("perpendicular");
  });

  it("threads explicit per-node/per-link color overrides through to the rendered trace", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({
        groupings: [
          {
            name: "n",
            label: "N",
            data: {
              nodes: [{ label: "A", color: "#2a78d6" }, { label: "B" }],
              links: [{ source: 0, target: 1, value: 5, color: "#e34948" }],
            },
          },
        ],
      }),
    );

    const el = document.createElement("mires-chart-sankey");
    el.setAttribute("data-url", "/fixture.json");
    document.body.appendChild(el);
    await waitForRenderCount(1);

    const [, traces] = reactMock.mock.calls[0] as [
      unknown,
      { node: { color: string[] }; link: { color: string[] } }[],
    ];
    expect(traces[0]?.node.color[0]).toBe("#2a78d6");
    expect(traces[0]?.link.color[0]).toBe("#e34948");
  });

  it("never carries a WebGL trace type — no gl variant exists at all for sankey (§5/§7.8)", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({
        groupings: [
          {
            name: "n",
            label: "N",
            data: {
              nodes: [{ label: "A" }, { label: "B" }],
              links: [{ source: 0, target: 1, value: 5 }],
            },
          },
        ],
      }),
    );

    const el = document.createElement("mires-chart-sankey");
    el.setAttribute("data-url", "/fixture.json");
    document.body.appendChild(el);
    await waitForRenderCount(1);

    const [, traces] = reactMock.mock.calls[0] as [unknown, { type: string }[]];
    expect(traces[0]?.type).toBe("sankey");
  });
});
