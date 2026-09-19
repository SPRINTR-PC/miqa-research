import { LitElement, css, html, nothing, type PropertyValues } from "lit";
import { property, state } from "lit/decorators.js";
import { ref } from "lit/directives/ref.js";
import Plotly from "plotly.js";
import type { Data, Layout, PlotlyHTMLElement } from "plotly.js";

import "../core-wc/kp-select.js";
import { chartPaletteStyles } from "./chart-palette-styles.js";
import { resolveChartCallback } from "./chart-callback-registry.js";
import { snakeToCamelDeep } from "./snake-to-camel.js";
import type {
  ChartCallbackEvent,
  ChartConfig,
  ChartGroupingLabels,
  ChartResponse,
  PlotlyTrace,
} from "./chart-types.js";

/**
 * Shared base class for every chart web component (CONTEXT.md: Chart
 * Grouping, Chart Config, Chart Data, WebGL Threshold, Chart Event Callback,
 * Chart Palette; `docs/charts-handoff.md` §3). Owns everything except one
 * abstract method — `buildTraces` — which a concrete chart-type element
 * implements to turn its own Chart Data shape into Plotly traces.
 *
 * `extraLayout()` and `fireCallback`'s `contextOverride` parameter exist from
 * the start (rather than being added later as amendments) because the wider
 * chart system already needs them: `extraLayout()` for a type's own layout
 * fields (e.g. bar's `barmode`), and the context override for the mixed-type
 * subplot grid to attribute an event to the specific subplot that fired it.
 */
export abstract class MiresChartBase<TData = unknown> extends LitElement {
  @property({ attribute: "data-url" })
  public dataUrl = "";

  /** Overrides the API response's `config.webglThreshold` when set. */
  @property({ type: Number, attribute: "webgl-threshold" })
  public webglThreshold?: number;

  /** Overrides the API response's `config.forceRenderer` when set. */
  @property({ attribute: "force-renderer" })
  public forceRenderer?: "svg" | "webgl" | "auto";

  @state()
  protected response?: ChartResponse<ChartConfig, TData>;

  @state()
  protected selectedGroupingIndex = 0;

  @state()
  protected loading = false;

  @state()
  protected error?: Error;

  private plotEl?: HTMLDivElement;
  private eventsWired = false;
  private suppressZoomCallback = false;

  private resizeObserver?: ResizeObserver;
  private darkModeQuery?: MediaQueryList;
  private themeAttributeObserver?: MutationObserver;

  private static instanceCounter = 0;
  private readonly instanceId = `mires-chart-${MiresChartBase.instanceCounter++}`;

  /** Only these 4 chart types have a WebGL-accelerated Plotly trace variant (docs/charts-handoff.md §5). */
  private static readonly GL_TRACE_MAP: Record<string, string> = {
    scatter: "scattergl",
    line: "scattergl",
    bubble: "scattergl",
    "filled-area": "scattergl",
  };

  protected get chartType(): string {
    return this.localName.replace(/^mires-chart-/, "");
  }

  /** Read-only introspection of the last-fetched, camelCase-converted response. */
  public get currentResponse(): ChartResponse<ChartConfig, TData> | undefined {
    return this.response;
  }

  /** Manually re-resolves the Chart Palette and re-renders — for a re-theming trigger this base class doesn't already listen for. */
  public refreshTheme = (): void => {
    this.renderPlot();
  };

  /** The only method a concrete chart-type element must implement. */
  protected abstract buildTraces(data: TData, labels?: ChartGroupingLabels): PlotlyTrace[];

  /** A type's own layout fields beyond trace construction (e.g. bar's `barmode`). Default: none. */
  protected extraLayout(): Partial<Layout> {
    return {

    };
  }

  public override connectedCallback(): void {
    super.connectedCallback();
    this.syncThemeAttribute();

    this.darkModeQuery = matchMedia("(prefers-color-scheme: dark)");
    this.darkModeQuery.addEventListener("change", this.handleColorSchemeChange);

    this.themeAttributeObserver = new MutationObserver(this.handleDocumentThemeChange);
    this.themeAttributeObserver.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["data-theme"],
    });

    this.resizeObserver = new ResizeObserver(this.handleResize);
    this.resizeObserver.observe(this);
  }

  public override disconnectedCallback(): void {
    super.disconnectedCallback();
    this.darkModeQuery?.removeEventListener("change", this.handleColorSchemeChange);
    this.darkModeQuery = undefined;
    this.themeAttributeObserver?.disconnect();
    this.themeAttributeObserver = undefined;
    this.resizeObserver?.disconnect();
    this.resizeObserver = undefined;
  }

  protected override updated(changed: PropertyValues): void {
    if (changed.has("dataUrl") && this.dataUrl) {
      void this.fetchData();
    }
    if ((changed.has("response") || changed.has("selectedGroupingIndex")) && this.response) {
      void this.renderPlot();
    }
  }

  private async fetchData(): Promise<void> {
    this.loading = true;
    this.error = undefined;
    try {
      const res = await fetch(this.dataUrl);
      if (!res.ok) {
        throw new Error(`Chart data request failed: ${res.status} ${res.statusText}`);
      }
      const raw: unknown = await res.json();
      this.response = snakeToCamelDeep<ChartResponse<ChartConfig, TData>>(raw);
      this.selectedGroupingIndex = 0;
    } catch (err) {
      this.error = err instanceof Error ? err : new Error(String(err));
    } finally {
      this.loading = false;
    }
  }

  private resolvedWebglThreshold(): number {
    return this.webglThreshold ?? this.response?.config?.webglThreshold ?? 100;
  }

  private resolvedForceRenderer(): "svg" | "webgl" | "auto" {
    return this.forceRenderer ?? this.response?.config?.forceRenderer ?? "auto";
  }

  /** Upgrades `baseType` to its WebGL variant above the resolved threshold; a documented no-op for the 7 types with none. */
  protected maybeUpgradeTraceType(baseType: string, pointCount: number): string {
    const glType = MiresChartBase.GL_TRACE_MAP[this.chartType];
    if (!glType) {
      return baseType;
    }
    const forced = this.resolvedForceRenderer();
    if (forced === "svg") {
      return baseType;
    }
    if (forced === "webgl") {
      return glType;
    }
    return pointCount > this.resolvedWebglThreshold() ? glType : baseType;
  }

  /**
   * A CSS custom property's raw value may still contain an unevaluated color
   * function (e.g. `hsl(from ... )`, used by the sequential/diverging ramps
   * and the gridline/axis colors) — custom properties only substitute var()
   * references, they don't evaluate color functions. Assigning the raw value
   * to a real color property on a throwaway probe element forces the browser
   * to fully resolve it.
   *
   * Protected rather than private: a concrete element whose trace-builder
   * needs resolved Chart Palette colors (heatmap, sankey — §7.6/§7.8) reads
   * them here rather than the base class hardcoding every type's own palette
   * subset.
   */
  protected resolveThemeColor(varName: string): string {
    const raw = getComputedStyle(this).getPropertyValue(varName).trim();
    if (!raw) {
      return "";
    }
    const probe = document.createElement("span");
    probe.style.color = raw;
    this.renderRoot.appendChild(probe);
    const resolved = getComputedStyle(probe).color;
    probe.remove();
    return resolved || raw;
  }

  /** Reads a numeric (pixel) CSS custom property — e.g. a `--mires-chart-padding-*` var — falling back when unset or unparsable. */
  private resolveThemeNumber(varName: string, fallback: number): number {
    const raw = getComputedStyle(this).getPropertyValue(varName).trim();
    if (!raw) {
      return fallback;
    }
    const parsed = Number.parseFloat(raw);
    return Number.isNaN(parsed) ? fallback : parsed;
  }

  private buildLayout(labels?: ChartGroupingLabels): Partial<Layout> {
    const style = getComputedStyle(this);
    const background = this.resolveThemeColor("--mires-color-background");
    const textColor = this.resolveThemeColor("--mires-form-color-text");
    const gridColor = this.resolveThemeColor("--mires-chart-gridline");
    const axisColor = this.resolveThemeColor("--mires-chart-axis");
    const colorway = [1, 2, 3, 4, 5, 6, 7, 8].map((i) => this.resolveThemeColor(`--mires-chart-series-${i}`));
    const fontFamily = style.getPropertyValue("--form-font-family").trim() || undefined;

    const topPadding = this.resolveThemeNumber("--mires-chart-padding-top", 16);
    const leftPadding = this.resolveThemeNumber("--mires-chart-padding-left", labels?.yAxisTitle ? 80 : 40);
    const bottomPadding = this.resolveThemeNumber("--mires-chart-padding-bottom", labels?.xAxisTitle ? 80 : 20);

    return {
      paper_bgcolor: background || undefined,
      plot_bgcolor: background || undefined,
      font: { family: fontFamily, color: textColor || undefined },
      colorway,
      margin: { t: topPadding, b: bottomPadding, l: leftPadding, r: 20 },
      xaxis: {
        title: labels?.xAxisTitle ? { text: labels.xAxisTitle } : undefined,
        color: axisColor || '#e1e1e1',
        gridcolor: gridColor || undefined,
        linecolor: axisColor || undefined,
        automargin: true,
        range: labels?.xAxisRange,
      },
      yaxis: {
        title: labels?.yAxisTitle ? { text: labels.yAxisTitle } : undefined,
        color: axisColor || '#e1e1e1',
        gridcolor: gridColor || undefined,
        linecolor: axisColor || undefined,
        automargin: true,
        range: labels?.yAxisRange,
      },
      legend: {
        font: { family: fontFamily, color: textColor || undefined },
        title: labels?.legendTitle ? { text: labels.legendTitle } : undefined,
      },
      ...this.extraLayout(),
    };
  }

  private async renderPlot(): Promise<void> {
    if (!this.response || !this.plotEl) {
      return;
    }
    const grouping = this.response.groupings[this.selectedGroupingIndex];
    const traces = this.buildTraces(grouping.data, grouping.labels);
    const layout = this.buildLayout(grouping.labels);
    const graphDiv = await Plotly.react(this.plotEl, traces as Data[], layout, { displaylogo: false, displayModeBar: false, responsive: true });
    this.syncPlotlyGlobalStyles();
    if (!this.eventsWired) {
      this.wireEvents(graphDiv);
      this.eventsWired = true;
    }
  }

  /**
   * plotly.js draws its own hover labels, select-box outline, and drag/hover
   * pointer-events rules (e.g. `.main-svg { pointer-events: none }` /
   * `.main-svg .draglayer { pointer-events: all }`) via a single stylesheet
   * it lazily appends to `document.head` (`Lib.addStyleRule`,
   * `#plotly.js-style-global`) — rules scoped to `.js-plotly-plot ...`
   * selectors, added to as more plotly.js features are first used. A
   * shadow root doesn't inherit `document.head` styles, so without a local
   * copy inside each chart's own shadow root, none of that interaction CSS
   * ever applies: hover never fires and drag-select never draws its
   * outline, even though the underlying event handling still runs. Re-synced
   * after every render since plotly.js can append more rules over time.
   */
  private syncPlotlyGlobalStyles(): void {
    const globalStyle = document.getElementById("plotly.js-style-global");
    if (!(globalStyle instanceof HTMLStyleElement) || !globalStyle.sheet) {
      return;
    }
    const cssText = Array.from(globalStyle.sheet.cssRules)
      .map((rule) => rule.cssText)
      .join("\n");
    let mirror = this.renderRoot.querySelector<HTMLStyleElement>("style[data-plotly-style-mirror]");
    if (!mirror) {
      mirror = document.createElement("style");
      mirror.dataset.plotlyStyleMirror = "";
      this.renderRoot.appendChild(mirror);
    }
    if (mirror.textContent !== cssText) {
      mirror.textContent = cssText;
    }
  }

  private wireEvents(graphDiv: PlotlyHTMLElement): void {
    graphDiv.on("plotly_click", (ev) => this.fireCallback("click", ev));
    graphDiv.on("plotly_relayout", (ev) => {
      if (!this.suppressZoomCallback) {
        this.fireCallback("zoom", ev);
      }
    });
  }

  /**
   * `contextOverride` lets a subclass (the mixed-type subplot grid) attribute
   * a fired event to something other than this element's own single
   * `chartType` — the single-chart case never passes it.
   */
  protected fireCallback(
    event: ChartCallbackEvent,
    raw: unknown,
    contextOverride?: { chartType?: string },
  ): void {
    const name = this.response?.config?.eventCallbacks?.[event];
    if (!name) {
      return;
    }
    const fn = resolveChartCallback(name);
    if (!fn) {
      console.warn(`Chart Event Callback "${name}" is not registered`);
      return;
    }
    fn({
      chartId: this.id || this.instanceId,
      chartType: contextOverride?.chartType ?? this.chartType,
      groupingName: this.response?.groupings[this.selectedGroupingIndex]?.name ?? "",
      event,
      raw,
    });
  }

  private handleResize = (): void => {
    if (!this.plotEl) {
      return;
    }
    this.suppressZoomCallback = true;
    Plotly.Plots.resize(this.plotEl);
    queueMicrotask(() => {
      this.suppressZoomCallback = false;
    });
  };

  private syncThemeAttribute(): void {
    const theme = document.documentElement.dataset.theme;
    if (theme) {
      this.dataset.theme = theme;
    } else {
      delete this.dataset.theme;
    }
  }

  private handleDocumentThemeChange = (): void => {
    this.syncThemeAttribute();
    void this.renderPlot();
  };

  private handleColorSchemeChange = (): void => {
    void this.renderPlot();
  };

  private handleGroupingChange = (event: CustomEvent<{ value: string }>): void => {
    this.selectedGroupingIndex = Number(event.detail.value);
  };

  private setPlotEl = (el?: Element): void => {
    this.plotEl = (el as HTMLDivElement | undefined) ?? undefined;
  };

  protected override render() {
    const groupings = this.response?.groupings ?? [];
    return html`
      ${groupings.length > 1
        ? html`<kp-select
            class="grouping-select"
            .options=${groupings.map((g, i) => ({ label: g.label, value: String(i) }))}
            .value=${String(this.selectedGroupingIndex)}
            @change=${this.handleGroupingChange}
          ></kp-select>`
        : nothing}
      ${this.loading ? html`<div class="chart-loading">Loading…</div>` : nothing}
      ${this.error ? html`<div class="chart-error">${this.error.message}</div>` : nothing}
      <div class="plot-container" ${ref(this.setPlotEl)}></div>
    `;
  }

  static override styles = [
    chartPaletteStyles,
    css`
      :host {
        position: relative;
        display: flex;
        flex-direction: column;
        width: 100%;
        height: 100%;
        min-height: 240px;

        /* Plot padding — the space reserved around the plot when the
           corresponding axis/plot title isn't present (see buildLayout()). */
        --mires-chart-padding-top: var(--chart-padding-top, 16);
        --mires-chart-padding-left: var(--chart-padding-left, 40);
        --mires-chart-padding-bottom: var(--chart-padding-bottom, 20);
      }
      .grouping-select {
        align-self: flex-end;
        max-width: 100%;
        margin-bottom: 8px;
        --kp-select-width: auto;
      }
      .plot-container {
        width: 100%;
        height: 100%;
        flex: 1 1 auto;
        min-height: 0;
      }
      .chart-loading,
      .chart-error {
        padding: var(--form-spacing-medium, 1rem);
      }
      .chart-error {
        color: var(--form-color-error, #dc3545);
      }
    `,
  ];
}
