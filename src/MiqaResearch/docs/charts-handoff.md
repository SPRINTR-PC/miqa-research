# Charting web components — handoff spec

Destination artifact for wayfinder map #70 ("Charting web components (Plotly.js) + serializers: architecture & API contract spec"). Consolidates every decision made across #71–#85 into one buildable spec for a new Plotly.js/Lit charting system: 11 chart types (pie/donut, line, scatter, bar, histogram, box, heatmap, 2D density, sankey, bubble, filled area), a mixed-type subplot wrapper, matching `MiqaResearch.data.serializers` modules, and a testing strategy. The whole map was plan-don't-do (#87) when written — **every section below is now fully shipped** (#88–#96; every TS interface, Lit component skeleton, and Python schema class matches what shipped, with no design deviations found during implementation). Treat this document as a design record of the charting component library running in the codebase today, not an open implementation task (matching `docs/prom-ocr-handoff.md`'s own already-shipped-pipeline framing).

Domain terms used throughout (**Chart Grouping**, **Chart Config**, **Chart Data**, **WebGL Threshold**, **Chart Event Callback**, **Chart Palette**, **Chart Grid**) are defined in `GLOSSARY.md`, along with ADRs 0020–0023 recording the cross-cutting decisions summarized here.

Lives in `.dev-data/webcomponents` (Lit + TS + Vite; `plotly.js` `^4.1.0` already a dependency, entry point `src/mireswc-charts.ts`, source under `src/charts/`) and `MiqaResearch/data/serializers/charts/` (django-ninja `Schema`, matching the existing convention already used by `MiqaResearch/data/serializers/participant_consent.py`).

**Out of scope** (ruled out on the map, not deferred): dashboard pages/views that consume these components, chart export/download, real-time/streaming chart updates (`dataUrl` is fetch-once-per-Grouping-change only), migrating any existing table/UI to use these charts, and a demo API view/URL route for manual testing (this spec covers Schema *classes*, not routing for a specific real dataset).

**Correction to the map's original design** (found while writing this spec, before any code existed — see `GLOSSARY.md` ADR 0020's amendment): the wayfinder map's grilling sessions assumed Django REST Framework (`serializers.Serializer`) for the Python side and a camelCase-rendering mixin at the wire boundary. Neither matches this codebase: every existing serializer module (`participant_consent.py`) already uses django-ninja's `Schema` (Pydantic-based), and no endpoint anywhere renders camelCase — wire format is plain snake_case JSON throughout the app. Both are corrected below; the TS-side interfaces and the overall architecture (§1, §3–§6, §8) are unaffected, since neither correction touches anything except the Python schema classes and where the snake↔camel conversion happens.

## 1. Architecture

**N independent Lit custom elements, one per chart type**, sharing an abstract base class — matches this package's existing one-element-per-concept style (`miqa-monitor`, `miqa-monitor-table`, `miqa-monitor-filter` are all separate elements already). A `<mires-chart-bar>` tag is self-documenting in markup in a way a single `<mires-chart type="bar">` element wouldn't be. Python mirrors this: a shared generic base `Schema` hierarchy (§2), one concrete `Schema` per chart type.

| Element | Chart type(s) | Contract | Ticket |
|---|---|---|---|
| `<mires-chart-line>` | Line | §7.1 | #77 |
| `<mires-chart-scatter>` | Scatter | §7.1 | #77 |
| `<mires-chart-bubble>` | Bubble | §7.1 | #77 |
| `<mires-chart-filled-area>` | Filled area | §7.1 | #77 |
| `<mires-chart-bar>` | Bar | §7.2 | #78 |
| `<mires-chart-histogram>` | Histogram | §7.3 | #79 |
| `<mires-chart-pie>` | Pie, donut | §7.4 | #80 |
| `<mires-chart-box>` | Box plot | §7.5 | #81 |
| `<mires-chart-heatmap>` | Heatmap | §7.6 | #82 |
| `<mires-chart-density-2d>` | 2D density (heatmap-style, contour-style) | §7.7 | #83 |
| `<mires-chart-sankey>` | Sankey | §7.8 | #84 |
| `<mires-chart-grid>` | Mixed-type subplots of any of the above | §8 | #75 |

Wire format is **plain snake_case JSON**, matching every other django-ninja endpoint in this codebase — no per-component rendering mixin, no new Pydantic aliasing convention introduced just for charts. `MiresChartBase` does one small snake_case→camelCase key conversion when it parses a fetched response (§3), so TS-side interfaces and property names stay camelCase internally without the wire format needing to be. Aggregation is **raw-values-by-default** — serializers send raw per-record values and let plotly.js bin/aggregate client-side (histogram, box, 2D density); server-side pre-aggregation is a documented opt-in escape hatch per type, never the default.

## 2. API contract: envelope, Chart Config vs. Chart Data (#74, ADR 0020)

Every `dataUrl` endpoint returns the same top-level shape, regardless of chart type:

```ts
interface ChartResponse<TConfig, TData> {
  config?: TConfig;
  groupings: ChartGrouping<TData>[]; // ALWAYS a non-empty array — never a distinct single-Grouping shape
}

interface ChartGrouping<TData> {
  name: string;   // stable machine key
  label: string;  // shown in the kp-select dropdown
  labels?: { xAxisTitle?: string; yAxisTitle?: string; legendTitle?: string }; // overrides Config defaults, per-Grouping
  data: TData;    // per-chart-type shape — §7
}
```

A chart with only one Chart Grouping renders with `groupings.length === 1` and no dropdown shown — one parsing path, no branching on response shape.

**Chart Config** = layout/behavior settings fixed across every Grouping in the response (WebGL override, event callback names, subplot layout, and each type's own layout knobs — §7). **Chart Data** = the actual trace values, which vary per Grouping, plus the optional per-Grouping `labels` override above (switching Grouping can change what's being measured, not only how it's sliced).

Base Config, shared by every chart type:

```ts
interface ChartConfig {
  webglThreshold?: number;                  // default 100 — see §5
  forceRenderer?: "svg" | "webgl" | "auto";  // bypasses the threshold entirely
  eventCallbacks?: { click?: string; zoom?: string }; // names resolved per §6
  subplot?: unknown;                         // only meaningful on <mires-chart-grid> — see §8
}
```

### Python base schemas (`MiqaResearch/data/serializers/charts/base.py`)

django-ninja `Schema` is a Pydantic model, which gives the base/per-type relationship a cleaner mechanism than DRF's 3-class-per-type subclassing would have needed: **Pydantic generics**. A concrete chart type only has to define its own `<Type>ChartDataSchema` and parametrize the shared generics — no per-type Grouping/Response subclass boilerplate.

```python
from typing import Generic, Literal, TypeVar
from ninja import Schema

TData = TypeVar("TData")

class ChartEventCallbacksSchema(Schema):
    click: str | None = None
    zoom: str | None = None

class ChartConfigSchema(Schema):
    webgl_threshold: int | None = None
    force_renderer: Literal["svg", "webgl", "auto"] | None = None
    event_callbacks: ChartEventCallbacksSchema | None = None
    subplot: dict | None = None  # only meaningful on the Chart Grid response — §8

class ChartGroupingLabelsSchema(Schema):
    x_axis_title: str | None = None
    y_axis_title: str | None = None
    legend_title: str | None = None

class ChartGroupingSchema(Schema, Generic[TData]):
    """Base for one Chart Grouping. Concrete chart-type response types parametrize this with their own Data schema."""
    name: str
    label: str
    labels: ChartGroupingLabelsSchema | None = None
    data: TData

class ChartResponseSchema(Schema, Generic[TData]):
    """Base for a chart dataUrl endpoint's response. Concrete chart-type response types parametrize this with their own Data schema."""
    config: ChartConfigSchema | None = None
    groupings: list[ChartGroupingSchema[TData]]
```

A concrete chart type (shown fully per type in §7) needs only its own `<Type>ChartDataSchema`, then either `<Type>ChartResponseSchema = ChartResponseSchema[<Type>ChartDataSchema]` (a plain type alias, for types with no Config fields of their own) or a small subclass overriding `config` with a `<Type>ChartConfigSchema(ChartConfigSchema)` (for types that need their own Config fields, e.g. bar's `bar_mode`).

No camelCase rendering step — schemas render as plain snake_case JSON like every other ninja endpoint (see the wire-format correction in §1); `MiresChartBase` (§3) converts snake_case keys to camelCase once when it parses the fetched response.

**Open item, flagged not resolved here**: confirm django-ninja correctly resolves a parametrized generic `Schema` (e.g. `ChartResponseSchema[BarChartDataSchema]`) when used as a route's `response=` type — this pattern is valid Pydantic and should work since ninja's response serialization is Pydantic-based, but isn't exercised anywhere else in this codebase today, so verify it during implementation before relying on it across all 11 types.

## 3. Shared base class: `MiresChartBase` (#76)

Every concrete chart-type element extends this. It owns everything except one abstract method:

```ts
export abstract class MiresChartBase<TData = unknown> extends LitElement {
  // Public API
  @property({ attribute: 'data-url' }) dataUrl!: string;
  @property({ type: Number, attribute: 'webgl-threshold' }) webglThreshold?: number;   // overrides API Config when set
  @property({ attribute: 'force-renderer' }) forceRenderer?: "svg" | "webgl" | "auto"; // overrides API Config when set
  get currentResponse(): ChartResponse<unknown, TData> | undefined { return this.response; } // read-only introspection
  refreshTheme = () => this.renderPlot();                                             // manual re-theme trigger

  @state() protected response?: ChartResponse<unknown, TData>;
  @state() protected selectedGroupingIndex = 0;
  @state() protected loading = false;
  @state() protected error?: Error;

  private plotEl?: HTMLDivElement;
  private resizeObserver?: ResizeObserver;
  private suppressZoomCallback = false; // guards Plotly.Plots.resize()-triggered relayouts — see §6

  private static readonly GL_TRACE_MAP: Record<string, string> = {
    scatter: 'scattergl', line: 'scattergl', bubble: 'scattergl', 'filled-area': 'scattergl',
  }; // per §5 — the other 7 chart types are simply absent from this map

  protected get chartType(): string { return this.localName.replace(/^mires-chart-/, ''); } // derived from tag name

  // Abstract — the ONLY thing a concrete chart-type element must implement
  protected abstract buildTraces(data: TData, labels?: ChartGroupingLabels): Partial<Plotly.Data>[];

  // Optional hooks a type may override (default no-ops)
  protected extraLayout(): Partial<Plotly.Layout> { return {}; } // added by #78 — a type's own layout fields (e.g. bar's barmode)

  // Lifecycle
  connectedCallback() { /* fetch dataUrl; ResizeObserver; matchMedia('(prefers-color-scheme: dark)') listener; data-theme MutationObserver */ }
  disconnectedCallback() { /* tear all of the above down */ }
  updated(changed: PropertyValues) { if (changed.has('dataUrl')) this.fetchData(); }

  private async fetchData() { /* fetch → JSON.parse → snakeToCamelDeep() (wire format is snake_case, per §2) → ChartResponse → renderPlot() */ }
  private onGroupingChange(i: number) { this.selectedGroupingIndex = i; this.renderPlot(); } // no refetch

  private resolvedWebglThreshold() { return this.webglThreshold ?? this.response?.config?.webglThreshold ?? 100; }
  private resolvedForceRenderer()  { return this.forceRenderer  ?? this.response?.config?.forceRenderer  ?? "auto"; }

  protected maybeUpgradeTraceType(baseType: string, pointCount: number): string {
    const glType = MiresChartBase.GL_TRACE_MAP[this.chartType];
    if (!glType) return baseType; // documented no-op for the 7 types with no gl variant
    const forced = this.resolvedForceRenderer();
    if (forced === 'svg') return baseType;
    if (forced === 'webgl') return glType;
    return pointCount > this.resolvedWebglThreshold() ? glType : baseType;
  }

  private buildLayout(labels?: ChartGroupingLabels) {
    const style = getComputedStyle(this); // resolves Chart Palette — §4
    return {
      paper_bgcolor: style.getPropertyValue('--mires-color-background'),
      plot_bgcolor: style.getPropertyValue('--mires-color-background'),
      font: { family: style.getPropertyValue('--form-font-family'), color: style.getPropertyValue('--mires-form-color-text') },
      colorway: [1,2,3,4,5,6,7,8].map((i) => style.getPropertyValue(`--mires-chart-series-${i}`)),
      xaxis: { title: labels?.xAxisTitle, gridcolor: style.getPropertyValue('--mires-chart-gridline') },
      yaxis: { title: labels?.yAxisTitle, gridcolor: style.getPropertyValue('--mires-chart-gridline') },
      legend: { title: { text: labels?.legendTitle } },
      ...this.extraLayout(),
    };
  }

  private renderPlot() {
    if (!this.response || !this.plotEl) return;
    const grouping = this.response.groupings[this.selectedGroupingIndex];
    Plotly.react(this.plotEl, this.buildTraces(grouping.data, grouping.labels), this.buildLayout(grouping.labels), { responsive: true });
    this.wireEvents();
  }

  private wireEvents() {
    this.plotEl!.on('plotly_click', (ev) => this.fireCallback('click', ev));
    this.plotEl!.on('plotly_relayout', (ev) => { if (!this.suppressZoomCallback) this.fireCallback('zoom', ev); });
  }

  protected fireCallback(event: "click" | "zoom", raw: unknown, contextOverride?: { chartType?: string }) {
    // contextOverride added by #75 — lets <mires-chart-grid> attribute an event to the specific subplot that fired it
    const name = this.response?.config?.eventCallbacks?.[event];
    if (!name) return;
    const fn = resolveChartCallback(name); // the registry from §6
    if (!fn) { console.warn(`Chart Event Callback "${name}" is not registered`); return; }
    fn({
      chartId: this.id || this.instanceId,
      chartType: contextOverride?.chartType ?? this.chartType,
      groupingName: this.response!.groupings[this.selectedGroupingIndex].name,
      event, raw,
    });
  }

  private handleResize() {
    this.suppressZoomCallback = true;
    Plotly.Plots.resize(this.plotEl!);
    queueMicrotask(() => { this.suppressZoomCallback = false; });
  }

  render() {
    return html`
      ${this.response && this.response.groupings.length > 1 ? html`
        <kp-select class="grouping-select"
          .options=${this.response.groupings.map((g, i) => ({ label: g.label, value: String(i) }))}
          .value=${String(this.selectedGroupingIndex)}
          @change=${(e: CustomEvent) => this.onGroupingChange(Number(e.detail.value))}>
        </kp-select>` : ''}
      ${this.loading ? html`<div class="chart-loading">Loading…</div>` : ''}
      ${this.error ? html`<div class="chart-error">${this.error.message}</div>` : ''}
      <div class="plot-container" ${ref((el) => this.plotEl = el as HTMLDivElement)}></div>
    `;
  }

  static styles = css`
    :host { position: relative; display: block; width: 100%; height: 100%; min-height: 240px; }
    .grouping-select { position: absolute; top: 8px; right: 8px; z-index: 1; } /* top-right overlay */
    .plot-container { width: 100%; height: 100%; }
  `;
}
```

**Data source is `dataUrl`-only** — no inline `data` property, no second code path. **`kp-select`** (already built in this package) is reused for the Grouping dropdown, rendered as a top-right overlay only when `groupings.length > 1`.

**Amendment history** (both amendments already folded into the class above):
- **#78**: added `extraLayout()` — bar was the first type needing a per-type layout field (`barmode`) beyond trace construction.
- **#75**: `fireCallback` gained the `contextOverride` parameter — needed by `<mires-chart-grid>` (§8) to attribute an event to whichever subplot actually fired it. The single-chart case is unaffected.

**Trace-builder extraction (#75, ADR 0023)**: every concrete element's `buildTraces` is a thin wrapper delegating to an **exported pure function** (`buildBarTraces`, `buildPieTraces`, etc. — shown per type in §7), so `<mires-chart-grid>` can call the exact same implementation for a subplot instead of duplicating trace-construction logic. A builder that needs resolved Chart Palette colors (heatmap, sankey) takes them as a parameter rather than calling `getComputedStyle` itself, keeping it pure.

## 4. Chart Palette — theming (#71, ADR 0022; amended by #82, #84)

plotly.js has no native CSS-variable support — `MiresChartBase` resolves everything via `getComputedStyle` at render time (§3).

| Plotly concern | Source |
|---|---|
| Background | `--mires-color-background` (existing) |
| Text / font | `--mires-form-color-text`, `--form-font-family` (existing) |
| Categorical series (bar/line/pie/…) | `--mires-chart-series-1` … `-8` (new — see below) |
| Sequential ramp (heatmap/2D-density magnitude) | `--mires-chart-sequential-0` … `-5` (new — computed live) |
| Diverging ramp (heatmap polarity, §7.6) | `--mires-chart-diverging-negative` / `-neutral` / `-positive` (new — fixed, added by #82) |
| Gridlines / axis line | `--mires-chart-gridline`, `--mires-chart-axis` (new) |

**Categorical colors are a fixed, pre-validated 8-hue set** — the `dataviz` skill's own documented default, shipped **unmodified**: blue `#2a78d6`, orange `#eb6834`, aqua `#1baf7a`, yellow `#eda100`, magenta `#e87ba4`, green `#008300`, violet `#4a3aa7`, red `#e34948` (dark-mode steps in the skill's `palette.md`). **Brand-anchoring was tried and rejected**: running the skill's `validate_palette.js` against a reorder placing MiqaResearch's own primary (violet) and secondary (blue) hues adjacent to each other failed the dark-mode normal-vision floor (ΔE 9.8, below the 15-floor gate) and the CVD check (ΔE 1.9) — the two brand hues are too close once stepped for the dark surface. The stock order already opens on blue (kin to secondary) with violet at slot 7 (kin to primary), judged close enough without re-risking a validated set. A site overriding these variables is responsible for re-validating its own choice with the skill's script.

**The sequential ramp is computed live** from `--mires-color-primary-parts` via CSS relative-color syntax (matching the existing `--mires-color-background-darker` pattern in `styles.ts`) at 6 fixed lightness steps (e.g. L 95/80/65/50/35/20%, hue+saturation held from primary) — safe to derive from an arbitrary brand hue because a single-hue ramp only needs lightness monotonicity, not pairwise CVD separation, unlike the categorical set.

**The diverging ramp (added by #82) is fixed, not brand-derived** — same reasoning as the categorical set: polarity color needs a specific validated hue pairing (blue↔gray↔red, per the `dataviz` skill's diverging-pair guidance), not an arbitrary runtime hue. Heatmap (§7.6) is the only type using it so far, opting in per-chart via `config.colorScale`.

**Sankey is a documented exception** (added by #84): its node count is open-ended (routinely beyond the categorical set's 8 safe slots), so per-node identity was never the "small fixed set of series" case the categorical-palette restriction protects. `SankeyNode.color`/`SankeyLink.color` are optional explicit overrides (§7.8) — the only chart type where the API may set an arbitrary color.

**Re-theming**: components listen for `matchMedia('(prefers-color-scheme: dark)')` changes and observe the `data-theme` attribute on the document root; either triggers a re-resolve via `getComputedStyle` followed by `Plotly.react` (not a full re-init). A public `refreshTheme()` method (§3) covers any other site-specific trigger.

## 5. WebGL Threshold (#72, ADR 0020)

`config.webglThreshold` (default 100) is the datapoint count above which a component upgrades to a chart type's WebGL-accelerated Plotly trace; `config.forceRenderer` (`"svg" | "webgl" | "auto"`) bypasses the threshold entirely. Confirmed against plotly.js `^4.1.0`'s actual trace-type list (full findings: `docs/research/webgl-threshold-plotly-4.1.md`):

| Chart type | WebGL variant | Behavior |
|---|---|---|
| Line, scatter, bubble, filled area | `scattergl` | Upgrades above threshold (filled area's `fill` is supported by `scattergl` — no exception) |
| Pie/donut, bar, histogram, box, heatmap, sankey, 2D density | — none — | `webglThreshold`/`forceRenderer` are documented no-ops |

Every one of the 11 components exposes the same `webglThreshold`/`forceRenderer` config surface regardless of whether its type has a gl variant — consistency across the API surface over strict truthfulness per component. `heatmapgl` existed in plotly.js's history but was removed in v3.0.0, which is why heatmap is in the no-op list despite being the most magnitude/matrix-shaped type.

## 6. Chart Event Callback (#73, ADR 0021)

A named external JS function, specified in `config.eventCallbacks.click`/`.zoom`, that a component resolves and invokes on a `plotly_click` or `plotly_relayout` (zoom/pan/reset) event.

```ts
export type ChartCallbackEvent = "click" | "zoom";
export interface ChartCallbackPayload {
  chartId: string; chartType: string; groupingName: string; event: ChartCallbackEvent; raw: unknown;
}
export type ChartCallback = (payload: ChartCallbackPayload) => void;

export function registerChartCallback(name: string, fn: ChartCallback): void;
export function unregisterChartCallback(name: string): void;
// also attached for plain <script> consumers: window.mires.registerChartCallback / .unregisterChartCallback
```

**Resolution is against this client-side registry only** — never a raw `window[name]` lookup or `eval`. Resolution is **lazy**: a component looks the name up only when the event actually fires, not at connect-time or fetch-time, so the host page only needs to register before the user *interacts*, not before the chart *renders* — this eliminates most script-load-order races structurally. An unresolved name logs one `console.warn` and no-ops; it never throws.

`click` → `plotly_click` only. `zoom` → `plotly_relayout` only (covers double-click-to-reset for free). Legend clicks are excluded from both. `MiresChartBase`'s own `Plotly.Plots.resize()` calls (container-resize responsiveness) are guarded (`suppressZoomCallback`, §3) so they never spuriously fire the "zoom" callback.

**Security property**: because resolution is only ever against the client-side registry, a compromised or malicious API response can at worst reference a name nobody registered (harmless no-op) or a function the host page already explicitly chose to expose — it can never make the browser execute code the page didn't opt into.

## 7. Per-chart-type contracts

### 7.1 XY line-family: line, scatter, bubble, filled area (#77)

These four are all plotly.js's `scatter` trace type distinguished only by `mode` and `fill` — one shared Chart Data shape and one shared intermediate base class:

```ts
interface XYSeries {
  name: string;
  x: (number | string)[];   // raw JSON scalars — numeric, categorical, or datetime-string; no server coercion
  y: number[];
  size?: number[];          // bubble only — marker size per point
  fill?: "none" | "tozeroy" | "tonexty"; // filled-area only; others default "none"
}
interface XYChartData { series: XYSeries[]; } // one Plotly trace per entry, in array order
```

No `color` field — colors always come from the categorical colorway (§4) in series order via `layout.colorway`, never an API-supplied hex; a per-series override would let a careless API response silently break ADR 0022's colorblind-safety guarantee. (**Note**: this policy does not extend to sankey, §7.8/§4 — sankey's open-ended node count is a different case.)

```ts
export function buildXYTraces(data: XYChartData, mode: "lines"|"markers"|"lines+markers", defaultFill: "none"|"tozeroy"|"tonexty" = "none"): Partial<Plotly.Data>[] {
  return data.series.map((s) => ({
    type: "scattergl" /* or "scatter" — resolved by the calling element's maybeUpgradeTraceType */,
    mode, name: s.name, x: s.x, y: s.y,
    marker: s.size ? { size: s.size } : undefined,
    fill: s.fill ?? defaultFill,
  }));
}
export const buildLineTraces = (d: XYChartData) => buildXYTraces(d, "lines");
export const buildScatterTraces = (d: XYChartData) => buildXYTraces(d, "markers");
export const buildBubbleTraces = (d: XYChartData) => buildXYTraces(d, "markers");
export const buildFilledAreaTraces = (d: XYChartData) => buildXYTraces(d, "lines", "tozeroy");

export abstract class XYChartBase extends MiresChartBase<XYChartData> {
  protected abstract get mode(): "lines" | "markers" | "lines+markers";
  protected get defaultFill(): "none" | "tozeroy" | "tonexty" { return "none"; }
  protected buildTraces(data: XYChartData) {
    return buildXYTraces(data, this.mode, this.defaultFill).map((t) => ({ ...t, type: this.maybeUpgradeTraceType("scatter", data.series.reduce((n, s) => n + s.x.length, 0)) }));
  }
}
@customElement('mires-chart-line')        class MiresChartLine extends XYChartBase        { protected get mode() { return "lines" as const; } }
@customElement('mires-chart-scatter')     class MiresChartScatter extends XYChartBase     { protected get mode() { return "markers" as const; } }
@customElement('mires-chart-bubble')      class MiresChartBubble extends XYChartBase      { protected get mode() { return "markers" as const; } } // series[].size expected
@customElement('mires-chart-filled-area') class MiresChartFilledArea extends XYChartBase  { protected get mode() { return "lines" as const; } protected get defaultFill() { return "tozeroy" as const; } }
```

WebGL: all 4 route through `scattergl` above threshold — confirmed no exception (§5).

Schemas — one shared Data schema, 4 thin response aliases:

```python
class XYSeriesSchema(Schema):
    name: str
    x: list[int | float | str]
    y: list[float]
    size: list[float] | None = None
    fill: Literal["none", "tozeroy", "tonexty"] | None = None

class XYChartDataSchema(Schema):
    series: list[XYSeriesSchema]

LineChartResponseSchema = ChartResponseSchema[XYChartDataSchema]
ScatterChartResponseSchema = ChartResponseSchema[XYChartDataSchema]
BubbleChartResponseSchema = ChartResponseSchema[XYChartDataSchema]
FilledAreaChartResponseSchema = ChartResponseSchema[XYChartDataSchema]
# 4 distinct aliases over the same XYChartDataSchema — for symmetry with the 4 distinct Lit
# elements and 4 distinct routes, not because the underlying shape differs.
```

### 7.2 Bar (#78)

```ts
interface BarSeries { name: string; values: number[]; } // aligned with `categories`
interface BarChartData { categories: string[]; series: BarSeries[]; } // length 1 = plain (non-grouped/stacked) bar chart
interface BarChartConfig extends ChartConfig {
  barMode?: "group" | "stack"; // default "group" — named after plotly.js's own layout.barmode
  orientation?: "v" | "h";      // default "v"
}
```

```ts
export function buildBarTraces(data: BarChartData, config?: BarChartConfig): Partial<Plotly.Data>[] {
  const orientation = config?.orientation ?? "v";
  return data.series.map((s) => ({
    type: "bar", orientation, name: s.name,
    x: orientation === "v" ? data.categories : s.values,
    y: orientation === "v" ? s.values : data.categories,
  }));
}
@customElement('mires-chart-bar')
class MiresChartBar extends MiresChartBase<BarChartData> {
  protected buildTraces(data: BarChartData) { return buildBarTraces(data, this.response?.config as BarChartConfig).map((t) => ({ ...t, type: this.maybeUpgradeTraceType("bar", 0) })); }
  protected extraLayout() { return { barmode: (this.response?.config as BarChartConfig)?.barMode ?? "group" }; }
}
```

WebGL: no-op (no gl variant for bar).

```python
class BarSeriesSchema(Schema):
    name: str
    values: list[float]
class BarChartDataSchema(Schema):
    categories: list[str]
    series: list[BarSeriesSchema]
class BarChartConfigSchema(ChartConfigSchema):
    bar_mode: Literal["group", "stack"] | None = None
    orientation: Literal["v", "h"] | None = None
class BarChartResponseSchema(ChartResponseSchema[BarChartDataSchema]):
    config: BarChartConfigSchema | None = None
```

(This ticket established the per-type `ChartConfigSchema` subclass pattern every later type follows — a type with its own Config fields overrides `config` on top of `ChartResponseSchema[<Type>ChartDataSchema]`.)

### 7.3 Histogram (#79)

```ts
interface HistogramBins { nbinsx?: number; start?: number; end?: number; size?: number; }
interface HistogramSeries { name: string; values: number[]; bins?: HistogramBins; } // raw values; bins overrides config default
interface HistogramChartData { series: HistogramSeries[]; }
interface HistogramChartConfig extends ChartConfig {
  histogramBins?: HistogramBins;  // chart-wide default binning
  orientation?: "v" | "h";
  histnorm?: "" | "percent" | "probability" | "density" | "probability density";
}
```

```ts
export function buildHistogramTraces(data: HistogramChartData, config?: HistogramChartConfig): Partial<Plotly.Data>[] {
  const orientation = config?.orientation ?? "v";
  const histnorm = config?.histnorm ?? "";
  return data.series.map((s) => {
    const bins = s.bins ?? config?.histogramBins;
    return {
      type: "histogram", name: s.name, orientation, histnorm,
      ...(orientation === "v" ? { x: s.values } : { y: s.values }),
      ...(bins && orientation === "v" ? { nbinsx: bins.nbinsx, xbins: { start: bins.start, end: bins.end, size: bins.size } } : {}),
      ...(bins && orientation === "h" ? { nbinsy: bins.nbinsx, ybins: { start: bins.start, end: bins.end, size: bins.size } } : {}),
    };
  });
}
```

WebGL: no-op. Raw per-record values, no server pre-aggregation (no exception to §1's default).

```python
class HistogramBinsSchema(Schema):
    nbinsx: int | None = None
    start: float | None = None
    end: float | None = None
    size: float | None = None
class HistogramSeriesSchema(Schema):
    name: str
    values: list[float]
    bins: HistogramBinsSchema | None = None
class HistogramChartDataSchema(Schema):
    series: list[HistogramSeriesSchema]
class HistogramChartConfigSchema(ChartConfigSchema):
    histogram_bins: HistogramBinsSchema | None = None
    orientation: Literal["v", "h"] | None = None
    histnorm: Literal["", "percent", "probability", "density", "probability density"] | None = None
class HistogramChartResponseSchema(ChartResponseSchema[HistogramChartDataSchema]):
    config: HistogramChartConfigSchema | None = None
```

### 7.4 Pie / donut (#80)

```ts
interface PieChartData { labels: string[]; values: number[]; } // FLAT — no `series` wrapper; a pie has exactly one distribution per Grouping
interface PieChartConfig extends ChartConfig {
  hole?: number;   // 0 (default) = plain pie; e.g. 0.4-0.7 = donut. One component handles both.
  sort?: boolean;  // default true (plotly's own default); false preserves array order
  textinfo?: "label" | "value" | "percent" | "label+percent" | "label+value" | "value+percent" | "label+value+percent" | "none"; // default "label+percent"
}
```

```ts
export function buildPieTraces(data: PieChartData, config?: PieChartConfig): Partial<Plotly.Data>[] {
  return [{
    type: "pie", labels: data.labels, values: data.values,
    hole: config?.hole ?? 0, sort: config?.sort ?? true, textinfo: config?.textinfo ?? "label+percent",
  }];
}
```

WebGL: no-op. Slice colors come from the categorical colorway (one per label, in order) — no per-slice override.

```python
from pydantic import Field

class PieChartDataSchema(Schema):
    labels: list[str]
    values: list[float]
class PieChartConfigSchema(ChartConfigSchema):
    hole: float | None = Field(default=None, ge=0, le=1)  # 0 (default) = plain pie; 0.4-0.7 = donut
    sort: bool | None = None
    textinfo: Literal["label", "value", "percent", "label+percent", "label+value", "value+percent", "label+value+percent", "none"] | None = None
class PieChartResponseSchema(ChartResponseSchema[PieChartDataSchema]):
    config: PieChartConfigSchema | None = None
```

### 7.5 Box plot (#81)

```ts
interface BoxStats { q1: number; median: number; q3: number; lowerFence?: number; upperFence?: number; mean?: number; sd?: number; }
interface BoxEntry {
  name: string;          // category label
  group?: string;         // optional 2nd dimension — boxes sharing a group become one trace, side-by-side per category via boxmode:'group'
  values?: number[];       // raw values — default
  stats?: BoxStats;        // precomputed alternative (exactly one of values/stats per entry, enforced server-side)
}
interface BoxChartData { boxes: BoxEntry[]; }
interface BoxChartConfig extends ChartConfig { quartileMethod?: "linear" | "exclusive" | "inclusive"; orientation?: "v" | "h"; }
```

```ts
export function buildBoxTraces(data: BoxChartData, config?: BoxChartConfig): Partial<Plotly.Data>[] {
  const quartilemethod = config?.quartileMethod ?? "linear";
  const groups = groupBy(data.boxes, (b) => b.group ?? "__default__");
  return Object.entries(groups).map(([groupName, boxes]) => {
    const name = groupName === "__default__" ? undefined : groupName;
    if (boxes.some((b) => b.stats)) {
      return { type: "box", name, x: boxes.map((b) => b.name),
        q1: boxes.map((b) => b.stats!.q1), median: boxes.map((b) => b.stats!.median), q3: boxes.map((b) => b.stats!.q3),
        lowerfence: boxes.map((b) => b.stats!.lowerFence), upperfence: boxes.map((b) => b.stats!.upperFence) };
    }
    const x: string[] = [], y: number[] = [];
    for (const b of boxes) for (const v of b.values ?? []) { x.push(b.name); y.push(v); }
    return { type: "box", name, x, y, quartilemethod };
  });
}
```

Mixing precomputed and raw boxes *within the same group* isn't supported cleanly by plotly's trace model — all boxes in a group should consistently use one or the other. WebGL: no-op.

```python
from pydantic import model_validator

class BoxStatsSchema(Schema):
    q1: float
    median: float
    q3: float
    lower_fence: float | None = None
    upper_fence: float | None = None
    mean: float | None = None
    sd: float | None = None
class BoxEntrySchema(Schema):
    name: str
    group: str | None = None
    values: list[float] | None = None
    stats: BoxStatsSchema | None = None

    @model_validator(mode="after")
    def exactly_one_of_values_or_stats(self):
        if bool(self.values) == bool(self.stats):
            raise ValueError("Exactly one of `values` or `stats` is required.")
        return self
class BoxChartDataSchema(Schema):
    boxes: list[BoxEntrySchema]
class BoxChartConfigSchema(ChartConfigSchema):
    quartile_method: Literal["linear", "exclusive", "inclusive"] | None = None
    orientation: Literal["v", "h"] | None = None
class BoxChartResponseSchema(ChartResponseSchema[BoxChartDataSchema]):
    config: BoxChartConfigSchema | None = None
```

### 7.6 Heatmap (#82)

```ts
interface HeatmapChartData { z: number[][]; x?: (number | string)[]; y?: (number | string)[]; } // labels default to indices if omitted
interface HeatmapChartConfig extends ChartConfig { colorScale?: "sequential" | "diverging"; zMid?: number; } // diverging default zMid = 0
```

```ts
export function buildHeatmapTraces(data: HeatmapChartData, config: HeatmapChartConfig | undefined, colors: { sequential: string[]; diverging: [string, string, string] }): Partial<Plotly.Data>[] {
  const mode = config?.colorScale ?? "sequential";
  const colorscale = mode === "diverging"
    ? [[0, colors.diverging[0]], [0.5, colors.diverging[1]], [1, colors.diverging[2]]]
    : colors.sequential.map((c, i) => [i / (colors.sequential.length - 1), c]);
  return [{ type: "heatmap", z: data.z, x: data.x, y: data.y, colorscale, zmid: mode === "diverging" ? (config?.zMid ?? 0) : undefined }];
}
```

Cell text/annotations are left out of scope — hover tooltips (plotly.js default) already surface exact values, and in-cell text on a large matrix gets unreadable fast. Payload size for large matrices is documented advisory guidance for API authors, not a server-side downsampling mechanism (unlike histogram/box, a heatmap's `z` is inherently already a chosen resolution — there's no raw-records layer underneath to aggregate). WebGL: no-op (`heatmapgl` removed in plotly.js v3.0.0).

```python
class HeatmapChartDataSchema(Schema):
    z: list[list[float]]
    x: list[int | float | str] | None = None
    y: list[int | float | str] | None = None
class HeatmapChartConfigSchema(ChartConfigSchema):
    color_scale: Literal["sequential", "diverging"] | None = None
    z_mid: float | None = None
class HeatmapChartResponseSchema(ChartResponseSchema[HeatmapChartDataSchema]):
    config: HeatmapChartConfigSchema | None = None
```

### 7.7 2D density (#83)

One component, not two — `config.style` toggles the underlying trace type (mirrors §7.4/§7.2's precedent for closely-related variants):

```ts
interface Density2DBins { nbinsx?: number; nbinsy?: number; xbins?: { start?: number; end?: number; size?: number }; ybins?: { start?: number; end?: number; size?: number }; }
interface Density2DSeries { name: string; x: number[]; y: number[]; bins?: Density2DBins; } // raw scattered point pairs
interface Density2DChartData { series: Density2DSeries[]; } // multi-series in scope, like histogram
interface Density2DChartConfig extends ChartConfig { style?: "heatmap" | "contour"; densityBins?: Density2DBins; } // default "heatmap"
```

```ts
export function buildDensity2DTraces(data: Density2DChartData, config?: Density2DChartConfig): Partial<Plotly.Data>[] {
  const baseType = (config?.style ?? "heatmap") === "contour" ? "histogram2dcontour" : "histogram2d";
  return data.series.map((s) => {
    const bins = s.bins ?? config?.densityBins;
    return { type: baseType, name: s.name, x: s.x, y: s.y, nbinsx: bins?.nbinsx, nbinsy: bins?.nbinsy, xbins: bins?.xbins, ybins: bins?.ybins };
  });
}
```

Colorscale is **sequential only** — unlike heatmap, density has no natural polarity concept (always a magnitude/count). Boundary with heatmap: heatmap takes a pre-binned `z` matrix (server already decided bins); density takes raw scattered points and lets plotly.js bin them, consistent with raw-values-by-default. WebGL: no-op for either `histogram2d` or `histogram2dcontour`.

```python
class Density2DBinsSchema(Schema):
    nbinsx: int | None = None
    nbinsy: int | None = None
    xbins: dict | None = None
    ybins: dict | None = None
class Density2DSeriesSchema(Schema):
    name: str
    x: list[float]
    y: list[float]
    bins: Density2DBinsSchema | None = None
class Density2DChartDataSchema(Schema):
    series: list[Density2DSeriesSchema]
class Density2DChartConfigSchema(ChartConfigSchema):
    style: Literal["heatmap", "contour"] | None = None
    density_bins: Density2DBinsSchema | None = None
class Density2DChartResponseSchema(ChartResponseSchema[Density2DChartDataSchema]):
    config: Density2DChartConfigSchema | None = None
```

### 7.8 Sankey (#84)

Structurally different from every other type — a nodes+links graph, not x/y or categorical:

```ts
interface SankeyNode { label: string; color?: string; } // explicit override; defaults to a neutral tone when omitted — see the ADR 0022 exception (§4)
interface SankeyLink { source: number; target: number; value: number; color?: string; } // defaults to a translucent tint of the source node's color
interface SankeyChartData { nodes: SankeyNode[]; links: SankeyLink[]; }
interface SankeyChartConfig extends ChartConfig { orientation?: "h" | "v"; arrangement?: "snap" | "perpendicular" | "freeform" | "fixed"; }
```

```ts
export function buildSankeyTraces(data: SankeyChartData, config: SankeyChartConfig | undefined, defaultNodeColor: string): Partial<Plotly.Data>[] {
  const nodeColors = data.nodes.map((n) => n.color ?? defaultNodeColor);
  const linkColors = data.links.map((l) => l.color ?? withAlpha(nodeColors[l.source], 0.4));
  return [{
    type: "sankey",
    orientation: config?.orientation ?? "h",
    arrangement: config?.arrangement ?? "snap",
    node: { label: data.nodes.map((n) => n.label), color: nodeColors },
    link: { source: data.links.map((l) => l.source), target: data.links.map((l) => l.target), value: data.links.map((l) => l.value), color: linkColors },
  }];
}
```

(`withAlpha` is a small color-utility helper applying opacity to a resolved color string.) **Sankey is the one documented exception** to the "no per-item color override" policy (§4/§7.1) — its node count is open-ended, so per-node identity was never the "small fixed set of series" case that policy protects. Config/Data split fits without amendment (Config was always "layout/behavior fixed across the response," never literally axis-only). No gl variant exists at all for Sankey — not even routed through `maybeUpgradeTraceType`.

```python
class SankeyNodeSchema(Schema):
    label: str
    color: str | None = None
class SankeyLinkSchema(Schema):
    source: int
    target: int
    value: float
    color: str | None = None
class SankeyChartDataSchema(Schema):
    nodes: list[SankeyNodeSchema]
    links: list[SankeyLinkSchema]
class SankeyChartConfigSchema(ChartConfigSchema):
    orientation: Literal["h", "v"] | None = None
    arrangement: Literal["snap", "perpendicular", "freeform", "fixed"] | None = None
class SankeyChartResponseSchema(ChartResponseSchema[SankeyChartDataSchema]):
    config: SankeyChartConfigSchema | None = None
```

## 8. Mixed-type subplots: `<mires-chart-grid>` (#75, ADR 0023)

plotly.js only composes subplots within one figure/DOM node (its own native `grid` layout) — this can't be built by mounting several of §7's elements side by side. One combined `dataUrl`/envelope (reusing §2 unchanged) drives the whole grid; one Grouping dropdown switches every subplot together.

```ts
interface ChartGridSubplotSpec { type: string; row: number; col: number; config?: unknown; } // type matches each element's own chartType string
interface ChartGridConfig extends ChartConfig { rows: number; cols: number; subplots: ChartGridSubplotSpec[]; } // fixed layout, same for every Grouping
interface ChartGridData { subplots: unknown[]; } // one entry per subplot, same order as config.subplots, shaped per that subplot's own type
```

```ts
const TYPE_BUILDERS: Record<string, (data: unknown, config?: unknown, colors?: unknown) => Partial<Plotly.Data>[]> = {
  bar: buildBarTraces, line: buildLineTraces, scatter: buildScatterTraces, bubble: buildBubbleTraces,
  'filled-area': buildFilledAreaTraces, histogram: buildHistogramTraces, pie: buildPieTraces,
  box: buildBoxTraces, heatmap: buildHeatmapTraces, 'density-2d': buildDensity2DTraces, sankey: buildSankeyTraces,
};
const AXIS_LESS_TYPES = new Set(['pie', 'sankey']); // positioned via `domain`, not shared axes

@customElement('mires-chart-grid')
export class MiresChartGrid extends MiresChartBase<ChartGridData> {
  protected buildTraces(data: ChartGridData): Partial<Plotly.Data>[] {
    const gridConfig = this.response!.config as ChartGridConfig;
    const style = getComputedStyle(this); // resolved once, passed down to builders that need palette colors
    return gridConfig.subplots.flatMap((spec, i) => {
      const traces = TYPE_BUILDERS[spec.type](data.subplots[i], spec.config, style);
      const axisSuffix = i === 0 ? '' : String(i + 1);
      return traces.map((t) => AXIS_LESS_TYPES.has(spec.type)
        ? { ...t, domain: gridCellDomain(spec.row, spec.col, gridConfig.rows, gridConfig.cols) }
        : { ...t, xaxis: `x${axisSuffix}`, yaxis: `y${axisSuffix}` });
    });
  }
  protected extraLayout(): Partial<Plotly.Layout> {
    const { rows, cols } = this.response!.config as ChartGridConfig;
    return { grid: { rows, columns: cols, pattern: 'independent' } };
  }
  protected fireCallback(event: "click" | "zoom", raw: unknown) {
    const subplotIndex = resolveSubplotIndexFromEvent(raw); // maps Plotly's curveNumber/subplot id back to a grid position
    const spec = (this.response!.config as ChartGridConfig).subplots[subplotIndex];
    super.fireCallback(event, raw, { chartType: spec?.type }); // §3's contextOverride
  }
}
```

A mixed-subplot chart cannot mix Chart Groupings across its subplots — two subplots needing genuinely independent grouping selection belong in two separate chart instances, not one Chart Grid.

```python
class ChartGridSubplotSpecSchema(Schema):
    type: str
    row: int
    col: int
    config: dict | None = None
class ChartGridConfigSchema(ChartConfigSchema):
    rows: int
    cols: int
    subplots: list[ChartGridSubplotSpecSchema]
class ChartGridDataSchema(Schema):
    subplots: list[dict]
    # each entry validated loosely here; a view-level check can cross-validate entry i against
    # the concrete DataSchema for config.subplots[i].type (e.g. BarChartDataSchema) if stricter validation is wanted
class ChartGridResponseSchema(ChartResponseSchema[ChartGridDataSchema]):
    config: ChartGridConfigSchema | None = None
```

## 9. Testing strategy (#85)

- **Per-type trace-builder functions** (§7, §8): unit-tested in isolation, no DOM at all — each takes Chart Data (+ Config, + resolved colors where relevant) and asserts the returned Plotly trace objects against fixture input.
- **Base-class behaviors** (§3): integration-tested via a minimal test-only concrete subclass (e.g. `class TestChart extends MiresChartBase { protected buildTraces() { return FIXTURE_TRACES; } }`) mounted with `happy-dom` — decouples these tests from any real chart type's contract. Covers Grouping switching without refetch, WebGL threshold precedence, event-callback firing/guarding, re-theming triggers, and the subplot-attribution override.
- **`plotly.js` is mocked** in tests — assert `Plotly.react`/`newPlot` were called with the expected arguments, not that pixels rendered. `happy-dom` has no real canvas/WebGL context. **Real-browser visual verification (e.g. Playwright) is explicitly out of scope for this map** — a separate initiative.
- **Python schemas**: per-type schemas (§7) follow ordinary Django/ninja test conventions already used elsewhere in this codebase. The shared base schemas (§2) get their own dedicated test module, verifying the envelope shape and the generic-parametrization pattern (`ChartResponseSchema[SomeDataSchema]`), since every concrete type's correctness depends on that shared layer resolving correctly. On the TS side, the `snakeToCamelDeep` conversion utility (§3) gets its own focused unit tests (nested objects, arrays, already-camelCase keys left alone) since every fetch response passes through it.

## 10. Open items for the implementing session

- The `dataviz` skill's `validate_palette.js` should be re-run once (§4) as a sanity check when implementation actually wires the CSS variables to a Plotly config, to confirm nothing about the resolved hex values drifted from the documented defaults.
- Confirm django-ninja correctly resolves a parametrized generic `Schema` (§2) as a route's `response=` type — flagged there as unverified against this codebase's actual ninja version.
- `gridCellDomain` (§8) and `resolveSubplotIndexFromEvent` (§8) are named but not derived in this spec — small utility functions the implementing session will need to write (mapping a grid row/col to a Plotly `domain` fraction, and mapping a Plotly click/relayout event back to a subplot index via `curveNumber`/subplot axis id).
- `withAlpha` (§7.8) is likewise a named-but-undefined small color utility (apply opacity to a resolved CSS color string).
- `snakeToCamelDeep` (§3) is likewise named but not derived — a small recursive key-conversion utility applied once per fetched response, before it's treated as a `ChartResponse`.
