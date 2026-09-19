import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { ChartGroupingLabels } from "./chart-types.js";
import { registerChartCallback, unregisterChartCallback } from "./chart-callback-registry.js";

const reactMock = vi.fn();
const resizeMock = vi.fn();

vi.mock("plotly.js", () => {
  return {
    default: { react: reactMock, Plots: { resize: resizeMock } },
    react: reactMock,
    Plots: { resize: resizeMock },
  };
});

const { MiresChartBase } = await import("./mires-chart-base.js");

interface FixtureData {
  value: number;
}

/** No chart type maps to a WebGL trace — used for every test except the WebGL-threshold precedence one. */
class NoGlFixtureChart extends MiresChartBase<FixtureData> {
  public buildTracesCalls: { data: FixtureData; labels?: ChartGroupingLabels }[] = [];

  protected buildTraces(data: FixtureData, labels?: ChartGroupingLabels) {
    this.buildTracesCalls.push({ data, labels });
    return [{ type: "scatter", x: [data.value] }];
  }
}
customElements.define("mires-chart-fixture-no-gl", NoGlFixtureChart);

/**
 * Registered as "mires-chart-line" so `chartType` resolves to "line" — one of
 * the 4 keys in the base class's GL_TRACE_MAP — purely to exercise the WebGL
 * upgrade mechanism. Not related to (and not registered alongside) the real
 * `<mires-chart-line>` element, which this test file never imports.
 */
class GlFixtureChart extends MiresChartBase<FixtureData> {
  protected buildTraces(data: FixtureData) {
    return [{ type: this.maybeUpgradeTraceType("scatter", data.value) }];
  }
}
customElements.define("mires-chart-line", GlFixtureChart);

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

/** Polls until Plotly.react has been called at least `min` times — the fetch → state → Lit update → renderPlot chain spans several microtasks. */
async function waitForRenderCount(min: number): Promise<void> {
  await vi.waitFor(() => {
    if (reactMock.mock.calls.length < min) {
      throw new Error(`expected at least ${min} render(s), got ${reactMock.mock.calls.length}`);
    }
  });
}

describe("MiresChartBase", () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    reactMock.mockReset();
    resizeMock.mockReset();
    fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    delete document.documentElement.dataset.theme;
  });

  afterEach(() => {
    document.body.innerHTML = "";
    vi.unstubAllGlobals();
  });

  it("fetches dataUrl, converts snake_case keys, and renders the first Grouping", async () => {
    const { on, handlers } = graphDivHandlers();
    reactMock.mockResolvedValue({ on });
    fetchMock.mockResolvedValue(
      jsonResponse({
        groupings: [{ name: "by_site", label: "By Site", data: { value: 1 } }],
      }),
    );

    const el = document.createElement("mires-chart-fixture-no-gl") as NoGlFixtureChart;
    el.dataUrl = "/fixture.json";
    document.body.appendChild(el);
    await waitForRenderCount(1);

    expect(fetchMock).toHaveBeenCalledWith("/fixture.json");
    expect(el.buildTracesCalls).toHaveLength(1);
    expect(el.buildTracesCalls[0]?.data).toEqual({ value: 1 });
    expect(handlers.plotly_click).toBeTypeOf("function");
    expect(handlers.plotly_relayout).toBeTypeOf("function");
  });

  it("switches Chart Grouping without refetching", async () => {
    reactMock.mockResolvedValue({ on: vi.fn() });
    fetchMock.mockResolvedValue(
      jsonResponse({
        groupings: [
          { name: "by_site", label: "By Site", data: { value: 1 } },
          { name: "by_consent_type", label: "By Consent Type", data: { value: 2 } },
        ],
      }),
    );

    const el = document.createElement("mires-chart-fixture-no-gl") as NoGlFixtureChart;
    el.dataUrl = "/fixture.json";
    document.body.appendChild(el);
    await waitForRenderCount(1);

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(el.buildTracesCalls[0]?.data).toEqual({ value: 1 });

    const select = el.renderRoot.querySelector("kp-select");
    expect(select).not.toBeNull();
    select?.dispatchEvent(new CustomEvent("change", { detail: { value: "1" } }));
    await waitForRenderCount(2);

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(el.buildTracesCalls.at(-1)?.data).toEqual({ value: 2 });
  });

  it("does not render a Grouping dropdown when there is only one Grouping", async () => {
    reactMock.mockResolvedValue({ on: vi.fn() });
    fetchMock.mockResolvedValue(
      jsonResponse({ groupings: [{ name: "only", label: "Only", data: { value: 1 } }] }),
    );

    const el = document.createElement("mires-chart-fixture-no-gl") as NoGlFixtureChart;
    el.dataUrl = "/fixture.json";
    document.body.appendChild(el);
    await waitForRenderCount(1);

    expect(el.renderRoot.querySelector("kp-select")).toBeNull();
  });

  describe("axis range", () => {
    it("leaves xaxis/yaxis range unset (Plotly autorange) when labels omit it", async () => {
      reactMock.mockResolvedValue({ on: vi.fn() });
      fetchMock.mockResolvedValue(
        jsonResponse({ groupings: [{ name: "only", label: "Only", data: { value: 1 } }] }),
      );

      const el = document.createElement("mires-chart-fixture-no-gl") as NoGlFixtureChart;
      el.dataUrl = "/fixture.json";
      document.body.appendChild(el);
      await waitForRenderCount(1);

      const [, , layout] = reactMock.mock.calls[0] as [
        unknown,
        unknown,
        { xaxis: { range?: unknown }; yaxis: { range?: unknown } },
      ];
      expect(layout.xaxis.range).toBeUndefined();
      expect(layout.yaxis.range).toBeUndefined();
    });

    it("applies labels.xAxisRange/yAxisRange to the Plotly layout when set", async () => {
      reactMock.mockResolvedValue({ on: vi.fn() });
      fetchMock.mockResolvedValue(
        jsonResponse({
          groupings: [
            {
              name: "only",
              label: "Only",
              labels: { x_axis_range: [0, 10], y_axis_range: [-5, 5] },
              data: { value: 1 },
            },
          ],
        }),
      );

      const el = document.createElement("mires-chart-fixture-no-gl") as NoGlFixtureChart;
      el.dataUrl = "/fixture.json";
      document.body.appendChild(el);
      await waitForRenderCount(1);

      const [, , layout] = reactMock.mock.calls[0] as [
        unknown,
        unknown,
        { xaxis: { range?: unknown }; yaxis: { range?: unknown } },
      ];
      expect(layout.xaxis.range).toEqual([0, 10]);
      expect(layout.yaxis.range).toEqual([-5, 5]);
    });

    it("passes a null range endpoint through unchanged, leaving that end on Plotly's autorange", async () => {
      reactMock.mockResolvedValue({ on: vi.fn() });
      fetchMock.mockResolvedValue(
        jsonResponse({
          groupings: [
            {
              name: "only",
              label: "Only",
              labels: { y_axis_range: [0, null] },
              data: { value: 1 },
            },
          ],
        }),
      );

      const el = document.createElement("mires-chart-fixture-no-gl") as NoGlFixtureChart;
      el.dataUrl = "/fixture.json";
      document.body.appendChild(el);
      await waitForRenderCount(1);

      const [, , layout] = reactMock.mock.calls[0] as [
        unknown,
        unknown,
        { xaxis: { range?: unknown }; yaxis: { range?: unknown } },
      ];
      expect(layout.xaxis.range).toBeUndefined();
      expect(layout.yaxis.range).toEqual([0, null]);
    });
  });

  describe("WebGL threshold precedence", () => {
    it("upgrades above the default threshold (100) when nothing overrides it", async () => {
      reactMock.mockResolvedValue({ on: vi.fn() });
      fetchMock.mockResolvedValue(
        jsonResponse({ groupings: [{ name: "n", label: "N", data: { value: 101 } }] }),
      );

      const el = document.createElement("mires-chart-line") as GlFixtureChart;
      el.dataUrl = "/fixture.json";
      document.body.appendChild(el);
      await waitForRenderCount(1);

      expect(reactMock).toHaveBeenCalledWith(
        expect.anything(),
        [{ type: "scattergl" }],
        expect.anything(),
        expect.anything(),
      );
    });

    it("stays under the API config's threshold value when the point count doesn't exceed it", async () => {
      reactMock.mockResolvedValue({ on: vi.fn() });
      fetchMock.mockResolvedValue(
        jsonResponse({
          config: { webgl_threshold: 500 },
          groupings: [{ name: "n", label: "N", data: { value: 200 } }],
        }),
      );

      const el = document.createElement("mires-chart-line") as GlFixtureChart;
      el.dataUrl = "/fixture.json";
      document.body.appendChild(el);
      await waitForRenderCount(1);

      expect(reactMock).toHaveBeenCalledWith(
        expect.anything(),
        [{ type: "scatter" }],
        expect.anything(),
        expect.anything(),
      );
    });

    it("lets a component attribute override the API config's threshold", async () => {
      reactMock.mockResolvedValue({ on: vi.fn() });
      fetchMock.mockResolvedValue(
        jsonResponse({
          config: { webgl_threshold: 500 },
          groupings: [{ name: "n", label: "N", data: { value: 200 } }],
        }),
      );

      const el = document.createElement("mires-chart-line") as GlFixtureChart;
      el.webglThreshold = 100;
      el.dataUrl = "/fixture.json";
      document.body.appendChild(el);
      await waitForRenderCount(1);

      expect(reactMock).toHaveBeenCalledWith(
        expect.anything(),
        [{ type: "scattergl" }],
        expect.anything(),
        expect.anything(),
      );
    });

    it("is a documented no-op for a chart type absent from the GL trace map", async () => {
      reactMock.mockResolvedValue({ on: vi.fn() });
      fetchMock.mockResolvedValue(
        jsonResponse({ groupings: [{ name: "n", label: "N", data: { value: 100000 } }] }),
      );

      const el = document.createElement("mires-chart-fixture-no-gl") as NoGlFixtureChart;
      el.dataUrl = "/fixture.json";
      document.body.appendChild(el);
      await waitForRenderCount(1);

      expect(reactMock).toHaveBeenCalledWith(
        expect.anything(),
        [{ type: "scatter", x: [100000] }],
        expect.anything(),
        expect.anything(),
      );
    });
  });

  describe("Chart Event Callback", () => {
    afterEach(() => {
      unregisterChartCallback("test-click-callback");
    });

    it("invokes a registered callback with a normalized payload on click", async () => {
      const { on, handlers } = graphDivHandlers();
      reactMock.mockResolvedValue({ on });
      fetchMock.mockResolvedValue(
        jsonResponse({
          config: { event_callbacks: { click: "test-click-callback" } },
          groupings: [{ name: "by_site", label: "By Site", data: { value: 1 } }],
        }),
      );
      const callback = vi.fn();
      registerChartCallback("test-click-callback", callback);

      const el = document.createElement("mires-chart-fixture-no-gl") as NoGlFixtureChart;
      el.id = "my-chart";
      el.dataUrl = "/fixture.json";
      document.body.appendChild(el);
      await waitForRenderCount(1);

      handlers.plotly_click?.({ points: [] });

      expect(callback).toHaveBeenCalledWith({
        chartId: "my-chart",
        chartType: "fixture-no-gl",
        groupingName: "by_site",
        event: "click",
        raw: { points: [] },
      });
    });

    it("warns and no-ops when the API names a callback nobody registered", async () => {
      const { on, handlers } = graphDivHandlers();
      reactMock.mockResolvedValue({ on });
      fetchMock.mockResolvedValue(
        jsonResponse({
          config: { event_callbacks: { click: "never-registered" } },
          groupings: [{ name: "n", label: "N", data: { value: 1 } }],
        }),
      );
      const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => undefined);

      const el = document.createElement("mires-chart-fixture-no-gl") as NoGlFixtureChart;
      el.dataUrl = "/fixture.json";
      document.body.appendChild(el);
      await waitForRenderCount(1);

      expect(() => handlers.plotly_click?.({})).not.toThrow();
      expect(warnSpy).toHaveBeenCalledWith(expect.stringContaining("never-registered"));

      warnSpy.mockRestore();
    });

    it("guards its own resize-triggered relayout from firing the zoom callback", async () => {
      let resizeCallback: (() => void) | undefined;
      class FakeResizeObserver {
        constructor(cb: () => void) {
          resizeCallback = cb;
        }
        observe(): void {}
        disconnect(): void {}
      }
      vi.stubGlobal("ResizeObserver", FakeResizeObserver);

      const { on, handlers } = graphDivHandlers();
      reactMock.mockResolvedValue({ on });
      fetchMock.mockResolvedValue(
        jsonResponse({
          config: { event_callbacks: { zoom: "test-click-callback" } },
          groupings: [{ name: "n", label: "N", data: { value: 1 } }],
        }),
      );
      const callback = vi.fn();
      registerChartCallback("test-click-callback", callback);

      const el = document.createElement("mires-chart-fixture-no-gl") as NoGlFixtureChart;
      el.dataUrl = "/fixture.json";
      document.body.appendChild(el);
      await waitForRenderCount(1);

      resizeCallback?.();
      expect(resizeMock).toHaveBeenCalledTimes(1);

      handlers.plotly_relayout?.({});
      expect(callback).not.toHaveBeenCalled();

      await vi.waitFor(() => {
        handlers.plotly_relayout?.({});
        expect(callback).toHaveBeenCalledTimes(1);
      });
    });
  });

  describe("re-theming", () => {
    it("mirrors the document's data-theme attribute onto itself and re-renders", async () => {
      reactMock.mockResolvedValue({ on: vi.fn() });
      fetchMock.mockResolvedValue(
        jsonResponse({ groupings: [{ name: "n", label: "N", data: { value: 1 } }] }),
      );

      const el = document.createElement("mires-chart-fixture-no-gl") as NoGlFixtureChart;
      el.dataUrl = "/fixture.json";
      document.body.appendChild(el);
      await waitForRenderCount(1);

      document.documentElement.dataset.theme = "dark";
      await vi.waitFor(() => {
        expect(el.dataset.theme).toBe("dark");
      });
      await waitForRenderCount(2);
    });

    it("registers a matchMedia dark-mode listener on connect", async () => {
      const matchMediaSpy = vi.spyOn(window, "matchMedia");
      reactMock.mockResolvedValue({ on: vi.fn() });
      fetchMock.mockResolvedValue(
        jsonResponse({ groupings: [{ name: "n", label: "N", data: { value: 1 } }] }),
      );

      const el = document.createElement("mires-chart-fixture-no-gl") as NoGlFixtureChart;
      el.dataUrl = "/fixture.json";
      document.body.appendChild(el);
      await waitForRenderCount(1);

      expect(matchMediaSpy).toHaveBeenCalledWith("(prefers-color-scheme: dark)");
      matchMediaSpy.mockRestore();
    });

    it("refreshTheme() re-renders on demand", async () => {
      reactMock.mockResolvedValue({ on: vi.fn() });
      fetchMock.mockResolvedValue(
        jsonResponse({ groupings: [{ name: "n", label: "N", data: { value: 1 } }] }),
      );

      const el = document.createElement("mires-chart-fixture-no-gl") as NoGlFixtureChart;
      el.dataUrl = "/fixture.json";
      document.body.appendChild(el);
      await waitForRenderCount(1);

      el.refreshTheme();
      await waitForRenderCount(2);
    });
  });
});
