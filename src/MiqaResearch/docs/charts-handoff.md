# Charting web components — handoff spec

Destination artifact for wayfinder map #70 ("Charting web components (Plotly.js) + serializers: architecture & API contract spec"). Consolidates every decision made across #71–#85 into one buildable spec for a new Plotly.js/Lit charting system: 11 chart types (pie/donut, line, scatter, bar, histogram, box, heatmap, 2D density, sankey, bubble, filled area), a mixed-type subplot wrapper, matching `MiqaResearch.data.serializers` modules, and a testing strategy. The whole map was plan-don't-do — **nothing below is implemented yet**; this is the design record an implementing session builds against, not a description of shipped code (contrast `docs/prom-ocr-handoff.md`, most of which documents an already-shipped pipeline).

Domain terms used throughout (**Chart Grouping**, **Chart Config**, **Chart Data**, **WebGL Threshold**, **Chart Event Callback**, **Chart Palette**, **Chart Grid**) are defined in `CONTEXT.md`, along with ADRs 0020–0023 recording the cross-cutting decisions summarized here.

Lives in `.dev-data/webcomponents` (Lit + TS + Vite; `plotly.js` `^4.1.0` already a dependency, entry point `src/mireswc-charts.ts`, source under `src/charts/`) and `MiqaResearch/data/serializers/charts/` (DRF).

**Out of scope** (ruled out on the map, not deferred): dashboard pages/views that consume these components, chart export/download, real-time/streaming chart updates (`dataUrl` is fetch-once-per-Grouping-change only), migrating any existing table/UI to use these charts, and a demo DRF view/URL route for manual testing (this spec covers serializer *classes*, not routing for a specific real dataset).

## 1. Architecture

**N independent Lit custom elements, one per chart type**, sharing an abstract base class — matches this package's existing one-element-per-concept style (`miqa-monitor`, `miqa-monitor-table`, `miqa-monitor-filter` are all separate elements already). A `<mires-chart-bar>` tag is self-documenting in markup in a way a single `<mires-chart type="bar">` element wouldn't be. Python mirrors this: a shared base serializer/mixin, one concrete serializer per chart type.

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

Wire format is **camelCase end-to-end** — Python serializer fields stay idiomatic snake_case; a shared camelCase-rendering mixin (e.g. `djangorestframework-camel-case`, confirmed available during implementation) converts only at the wire boundary. Aggregation is **raw-values-by-default** — serializers send raw per-record values and let plotly.js bin/aggregate client-side (histogram, box, 2D density); server-side pre-aggregation is a documented opt-in escape hatch per type, never the default.

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

### Python base serializers (`MiqaResearch/data/serializers/charts/base.py`)

```python
from rest_framework import serializers

class ChartEventCallbacksSerializer(serializers.Serializer):
    click = serializers.CharField(required=False, allow_null=True)
    zoom = serializers.CharField(required=False, allow_null=True)

class ChartConfigSerializer(serializers.Serializer):
    webgl_threshold = serializers.IntegerField(required=False)
    force_renderer = serializers.ChoiceField(choices=["svg", "webgl", "auto"], required=False)
    event_callbacks = ChartEventCallbacksSerializer(required=False)
    subplot = serializers.DictField(required=False)  # only meaningful on the Chart Grid response — §8

class ChartGroupingLabelsSerializer(serializers.Serializer):
    x_axis_title = serializers.CharField(required=False)
    y_axis_title = serializers.CharField(required=False)
    legend_title = serializers.CharField(required=False)

class ChartGroupingSerializer(serializers.Serializer):
    """Base for one Chart Grouping. Concrete chart-type serializers subclass this and override `data`."""
    name = serializers.CharField()
    label = serializers.CharField()
    labels = ChartGroupingLabelsSerializer(required=False)
    data = serializers.DictField()  # overridden per concrete chart type

class ChartResponseSerializer(serializers.Serializer):
    """Base for a chart dataUrl endpoint's response. Concrete chart-type serializers subclass this and override `groupings`."""
    config = ChartConfigSerializer(required=False)
    groupings = ChartGroupingSerializer(many=True)
```

Every concrete chart-type serializer follows the same subclassing pattern (shown fully per type in §7): a `<Type>ChartDataSerializer`, a `<Type>ChartGroupingSerializer(ChartGroupingSerializer)` overriding `data`, and a `<Type>ChartResponseSerializer(ChartResponseSerializer)` overriding `groupings` (and `config`, where the type has its own Config fields).

Apply the shared camelCase-rendering mixin to every chart view/serializer so the wire format matches the TS interfaces above exactly, with no per-component transform code.

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

  private async fetchData() { /* fetch → parsed ChartResponse (already camelCase, per §2) → renderPlot() */ }
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

Serializers — one shared Data serializer, 4 thin response wrappers:

```python
class XYSeriesSerializer(serializers.Serializer):
    name = serializers.CharField()
    x = serializers.ListField(child=serializers.JSONField())
    y = serializers.ListField(child=serializers.FloatField())
    size = serializers.ListField(child=serializers.FloatField(), required=False)
    fill = serializers.ChoiceField(choices=["none", "tozeroy", "tonexty"], required=False)

class XYChartDataSerializer(serializers.Serializer):
    series = XYSeriesSerializer(many=True)

class LineChartGroupingSerializer(ChartGroupingSerializer):
    data = XYChartDataSerializer()
class LineChartResponseSerializer(ChartResponseSerializer):
    groupings = LineChartGroupingSerializer(many=True)
# ScatterChartResponseSerializer / BubbleChartResponseSerializer / FilledAreaChartResponseSerializer:
# identical shape, reusing XYChartDataSerializer/XYSeriesSerializer — 4 distinct classes for symmetry
# with the 4 distinct Lit elements, not because the underlying shape differs.
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
class BarSeriesSerializer(serializers.Serializer):
    name = serializers.CharField()
    values = serializers.ListField(child=serializers.FloatField())
class BarChartDataSerializer(serializers.Serializer):
    categories = serializers.ListField(child=serializers.CharField())
    series = BarSeriesSerializer(many=True)
class BarChartConfigSerializer(ChartConfigSerializer):
    bar_mode = serializers.ChoiceField(choices=["group", "stack"], required=False)
    orientation = serializers.ChoiceField(choices=["v", "h"], required=False)
class BarChartGroupingSerializer(ChartGroupingSerializer):
    data = BarChartDataSerializer()
class BarChartResponseSerializer(ChartResponseSerializer):
    config = BarChartConfigSerializer(required=False)
    groupings = BarChartGroupingSerializer(many=True)
```

(This ticket established the per-type `ChartConfigSerializer` subclass pattern every later type follows.)

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
class HistogramBinsSerializer(serializers.Serializer):
    nbinsx = serializers.IntegerField(required=False)
    start = serializers.FloatField(required=False); end = serializers.FloatField(required=False); size = serializers.FloatField(required=False)
class HistogramSeriesSerializer(serializers.Serializer):
    name = serializers.CharField()
    values = serializers.ListField(child=serializers.FloatField())
    bins = HistogramBinsSerializer(required=False)
class HistogramChartDataSerializer(serializers.Serializer):
    series = HistogramSeriesSerializer(many=True)
class HistogramChartConfigSerializer(ChartConfigSerializer):
    histogram_bins = HistogramBinsSerializer(required=False)
    orientation = serializers.ChoiceField(choices=["v", "h"], required=False)
    histnorm = serializers.ChoiceField(choices=["", "percent", "probability", "density", "probability density"], required=False)
class HistogramChartGroupingSerializer(ChartGroupingSerializer):
    data = HistogramChartDataSerializer()
class HistogramChartResponseSerializer(ChartResponseSerializer):
    config = HistogramChartConfigSerializer(required=False)
    groupings = HistogramChartGroupingSerializer(many=True)
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
class PieChartDataSerializer(serializers.Serializer):
    labels = serializers.ListField(child=serializers.CharField())
    values = serializers.ListField(child=serializers.FloatField())
class PieChartConfigSerializer(ChartConfigSerializer):
    hole = serializers.FloatField(required=False, min_value=0, max_value=1)
    sort = serializers.BooleanField(required=False)
    textinfo = serializers.ChoiceField(choices=["label", "value", "percent", "label+percent", "label+value", "value+percent", "label+value+percent", "none"], required=False)
class PieChartGroupingSerializer(ChartGroupingSerializer):
    data = PieChartDataSerializer()
class PieChartResponseSerializer(ChartResponseSerializer):
    config = PieChartConfigSerializer(required=False)
    groupings = PieChartGroupingSerializer(many=True)
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
class BoxStatsSerializer(serializers.Serializer):
    q1 = serializers.FloatField(); median = serializers.FloatField(); q3 = serializers.FloatField()
    lower_fence = serializers.FloatField(required=False); upper_fence = serializers.FloatField(required=False)
    mean = serializers.FloatField(required=False); sd = serializers.FloatField(required=False)
class BoxEntrySerializer(serializers.Serializer):
    name = serializers.CharField()
    group = serializers.CharField(required=False, allow_null=True)
    values = serializers.ListField(child=serializers.FloatField(), required=False)
    stats = BoxStatsSerializer(required=False)
    def validate(self, attrs):
        if bool(attrs.get("values")) == bool(attrs.get("stats")):
            raise serializers.ValidationError("Exactly one of `values` or `stats` is required.")
        return attrs
class BoxChartDataSerializer(serializers.Serializer):
    boxes = BoxEntrySerializer(many=True)
class BoxChartConfigSerializer(ChartConfigSerializer):
    quartile_method = serializers.ChoiceField(choices=["linear", "exclusive", "inclusive"], required=False)
    orientation = serializers.ChoiceField(choices=["v", "h"], required=False)
class BoxChartGroupingSerializer(ChartGroupingSerializer):
    data = BoxChartDataSerializer()
class BoxChartResponseSerializer(ChartResponseSerializer):
    config = BoxChartConfigSerializer(required=False)
    groupings = BoxChartGroupingSerializer(many=True)
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
class HeatmapChartDataSerializer(serializers.Serializer):
    z = serializers.ListField(child=serializers.ListField(child=serializers.FloatField()))
    x = serializers.ListField(child=serializers.JSONField(), required=False)
    y = serializers.ListField(child=serializers.JSONField(), required=False)
class HeatmapChartConfigSerializer(ChartConfigSerializer):
    color_scale = serializers.ChoiceField(choices=["sequential", "diverging"], required=False)
    z_mid = serializers.FloatField(required=False)
class HeatmapChartGroupingSerializer(ChartGroupingSerializer):
    data = HeatmapChartDataSerializer()
class HeatmapChartResponseSerializer(ChartResponseSerializer):
    config = HeatmapChartConfigSerializer(required=False)
    groupings = HeatmapChartGroupingSerializer(many=True)
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
class Density2DBinsSerializer(serializers.Serializer):
    nbinsx = serializers.IntegerField(required=False); nbinsy = serializers.IntegerField(required=False)
    xbins = serializers.DictField(required=False); ybins = serializers.DictField(required=False)
class Density2DSeriesSerializer(serializers.Serializer):
    name = serializers.CharField()
    x = serializers.ListField(child=serializers.FloatField())
    y = serializers.ListField(child=serializers.FloatField())
    bins = Density2DBinsSerializer(required=False)
class Density2DChartDataSerializer(serializers.Serializer):
    series = Density2DSeriesSerializer(many=True)
class Density2DChartConfigSerializer(ChartConfigSerializer):
    style = serializers.ChoiceField(choices=["heatmap", "contour"], required=False)
    density_bins = Density2DBinsSerializer(required=False)
class Density2DChartGroupingSerializer(ChartGroupingSerializer):
    data = Density2DChartDataSerializer()
class Density2DChartResponseSerializer(ChartResponseSerializer):
    config = Density2DChartConfigSerializer(required=False)
    groupings = Density2DChartGroupingSerializer(many=True)
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
class SankeyNodeSerializer(serializers.Serializer):
    label = serializers.CharField()
    color = serializers.CharField(required=False, allow_null=True)
class SankeyLinkSerializer(serializers.Serializer):
    source = serializers.IntegerField(); target = serializers.IntegerField(); value = serializers.FloatField()
    color = serializers.CharField(required=False, allow_null=True)
class SankeyChartDataSerializer(serializers.Serializer):
    nodes = SankeyNodeSerializer(many=True)
    links = SankeyLinkSerializer(many=True)
class SankeyChartConfigSerializer(ChartConfigSerializer):
    orientation = serializers.ChoiceField(choices=["h", "v"], required=False)
    arrangement = serializers.ChoiceField(choices=["snap", "perpendicular", "freeform", "fixed"], required=False)
class SankeyChartGroupingSerializer(ChartGroupingSerializer):
    data = SankeyChartDataSerializer()
class SankeyChartResponseSerializer(ChartResponseSerializer):
    config = SankeyChartConfigSerializer(required=False)
    groupings = SankeyChartGroupingSerializer(many=True)
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
class ChartGridSubplotSpecSerializer(serializers.Serializer):
    type = serializers.CharField(); row = serializers.IntegerField(); col = serializers.IntegerField()
    config = serializers.JSONField(required=False)
class ChartGridConfigSerializer(ChartConfigSerializer):
    rows = serializers.IntegerField(); cols = serializers.IntegerField()
    subplots = ChartGridSubplotSpecSerializer(many=True)
class ChartGridDataSerializer(serializers.Serializer):
    subplots = serializers.ListField(child=serializers.JSONField())
    # each entry validated loosely here; a view-level check can cross-validate entry i against
    # the concrete DataSerializer for config.subplots[i].type (e.g. BarChartDataSerializer) if stricter validation is wanted
class ChartGridGroupingSerializer(ChartGroupingSerializer):
    data = ChartGridDataSerializer()
class ChartGridResponseSerializer(ChartResponseSerializer):
    config = ChartGridConfigSerializer(required=False)
    groupings = ChartGridGroupingSerializer(many=True)
```

## 9. Testing strategy (#85)

- **Per-type trace-builder functions** (§7, §8): unit-tested in isolation, no DOM at all — each takes Chart Data (+ Config, + resolved colors where relevant) and asserts the returned Plotly trace objects against fixture input.
- **Base-class behaviors** (§3): integration-tested via a minimal test-only concrete subclass (e.g. `class TestChart extends MiresChartBase { protected buildTraces() { return FIXTURE_TRACES; } }`) mounted with `happy-dom` — decouples these tests from any real chart type's contract. Covers Grouping switching without refetch, WebGL threshold precedence, event-callback firing/guarding, re-theming triggers, and the subplot-attribution override.
- **`plotly.js` is mocked** in tests — assert `Plotly.react`/`newPlot` were called with the expected arguments, not that pixels rendered. `happy-dom` has no real canvas/WebGL context. **Real-browser visual verification (e.g. Playwright) is explicitly out of scope for this map** — a separate initiative.
- **Python serializers**: per-type serializers (§7) follow ordinary Django/DRF test conventions already used elsewhere in this codebase. The shared base serializers and camelCase mixin (§2) get their own dedicated test module, verifying the envelope shape and the snake_case↔camelCase conversion, since every other serializer's correctness depends on that shared layer.

## 10. Open items for the implementing session

- The `dataviz` skill's `validate_palette.js` should be re-run once (§4) as a sanity check when implementation actually wires the CSS variables to a Plotly config, to confirm nothing about the resolved hex values drifted from the documented defaults.
- Confirm `djangorestframework-camel-case` (or an equivalent) is an acceptable new dependency during implementation, or whether a small house-written camelCase mixin is preferred instead — this spec assumes one exists but doesn't mandate the specific package.
- `gridCellDomain` (§8) and `resolveSubplotIndexFromEvent` (§8) are named but not derived in this spec — small utility functions the implementing session will need to write (mapping a grid row/col to a Plotly `domain` fraction, and mapping a Plotly click/relayout event back to a subplot index via `curveNumber`/subplot axis id).
- `withAlpha` (§7.8) is likewise a named-but-undefined small color utility (apply opacity to a resolved CSS color string).
