# mireswc-charts

`mireswc-charts` is a set of framework-agnostic [Lit](https://lit.dev) web components
that wrap [plotly.js](https://plotly.com/javascript/) to render MIRES charts. Each
chart type is a custom element (`<mires-chart-line>`, `<mires-chart-bar>`, ...) that
fetches its own data from a URL, converts it to Plotly traces, and re-renders on
theme changes, resize, and Chart Grouping switches — no chart-specific glue code
needed in the host page.

This document is a user manual for consumers of the library: what each chart type
looks like, what JSON shape it expects, and how to drop it into a web page.

## Contents

- [Getting started](#getting-started)
- [Core concepts](#core-concepts)
- [Common attributes (all chart types)](#common-attributes-all-chart-types)
- [Theming](#theming)
- [Event callbacks](#event-callbacks)
- [Chart type reference](#chart-type-reference)
  - [Line](#line--mires-chart-line)
  - [Scatter](#scatter--mires-chart-scatter)
  - [Bubble](#bubble--mires-chart-bubble)
  - [Filled area](#filled-area--mires-chart-filled-area)
  - [Bar](#bar--mires-chart-bar)
  - [Histogram](#histogram--mires-chart-histogram)
  - [Pie](#pie--mires-chart-pie)
  - [Box](#box--mires-chart-box)
  - [Heatmap](#heatmap--mires-chart-heatmap)
  - [2D density](#2d-density--mires-chart-density-2d)
  - [Sankey](#sankey--mires-chart-sankey)
  - [Mixed-type grid](#mixed-type-grid--mires-chart-grid)
- [WebGL rendering](#webgl-rendering)
- [Local development / demo page](#local-development--demo-page)

## Getting started

This directory (`.dev-data/webcomponents`) is the source project. It's built with
Vite and outputs to `static/js/webcomponents/mireswc-charts.js` (see
`vite.config.ts`), which is what the MiqaResearch app actually serves.

```bash
npm install
npm run build      # emits ../../static/js/webcomponents/mireswc-charts.js
npm run dev        # Vite dev server + index.html demo (fixture data, no backend needed)
npm run test:run   # vitest
```

In a page, load the built bundle as a module and use the elements like any other
HTML tag:

```html
<script type="module" src="/static/js/webcomponents/mireswc-charts.js"></script>

<div style="width: 480px; height: 320px;">
  <mires-chart-line data-url="/api/charts/consents-over-time"></mires-chart-line>
</div>
```

Every chart element sizes itself to fill its parent — give the parent (or the
element itself) an explicit width and height.

## Core concepts

- **Chart Data** — the type-specific payload a chart renders (series of x/y
  points, bar categories, pie labels, sankey nodes/links, ...). Shape differs per
  chart type; see the [reference](#chart-type-reference) below.
- **Chart Grouping** — a named, labeled alternative view of the same underlying
  dataset (e.g. "By Site" vs. "By Consent Type"). A `dataUrl` response always
  returns a non-empty array of groupings; when there's more than one, the chart
  renders a dropdown so the user can switch between them. A single grouping
  renders with no dropdown.
- **Chart Config** — layout/behavior settings that apply to the whole response
  (not to any one grouping), e.g. `bar_mode`, `webgl_threshold`, or
  `event_callbacks`.
- **`data-url` response contract** — every chart element fetches JSON from its
  `data-url` attribute on connect and whenever that attribute changes:

  ```jsonc
  {
    "config": { /* optional, type-specific — see each chart type below */ },
    "groupings": [
      {
        "name": "by_site",              // stable identifier, e.g. for callbacks
        "label": "By Site",              // shown in the grouping dropdown
        "labels": {                      // optional axis/legend titles
          "x_axis_title": "Day",
          "y_axis_title": "Count",
          "legend_title": "Site"
        },
        "data": { /* type-specific Chart Data — see each chart type below */ }
      }
    ]
  }
  ```

  **JSON keys are `snake_case`.** The component converts the whole response to
  `camelCase` internally before use, so write your API/fixture JSON in
  `snake_case` as shown in every example below — don't pre-convert it.

- No chart type accepts inline data as an attribute or property — data always
  comes from `data-url`. For static/demo data, intercept `fetch` for that URL
  (see [Local development](#local-development--demo-page)) rather than trying to
  set a data property directly.

## Common attributes (all chart types)

Every `<mires-chart-*>` element supports:

| Attribute | Type | Description |
|---|---|---|
| `data-url` | string | URL the chart fetches its `ChartResponse` JSON from. Re-fetches when changed. |
| `webgl-threshold` | number | Overrides `config.webgl_threshold` from the response. Point count above which an eligible trace type switches to its WebGL-accelerated variant. Default 100. |
| `force-renderer` | `"svg" \| "webgl" \| "auto"` | Overrides `config.force_renderer`. `"auto"` (default) decides via the threshold; `"svg"`/`"webgl"` pin the renderer regardless of point count. |
| `id` | string | Standard HTML id. Used to identify the chart in [event callback](#event-callbacks) payloads (`chartId`); falls back to an internal instance id if omitted. |

Only **line, scatter, bubble, and filled area** have a WebGL variant
(`scattergl`) and respond to the threshold/force-renderer controls — see
[WebGL rendering](#webgl-rendering). For every other chart type these two
attributes are accepted but have no effect.

## Theming

Charts read their colors from CSS custom properties on the host element at
render time (via `getComputedStyle`), and automatically re-render when:

- the OS color scheme (`prefers-color-scheme`) changes, or
- `document.documentElement`'s `data-theme` attribute changes (an explicit
  light/dark toggle in the host app).

You don't need to do anything for this to work. To customize the palette, set
these custom properties anywhere the chart element inherits from (e.g. `:root`):

```css
:root {
  --chart-series-1: #2a78d6; /* categorical colors, 8 slots: --chart-series-1..8 */
  --chart-series-2: #eb6834;
  /* ... */
  --chart-sequential-0: #f2f2f2; /* sequential ramp, 6 stops: --chart-sequential-0..5 */
  /* ... */
  --chart-diverging-negative: #2a78d6; /* diverging ramp (heatmap only) */
  --chart-diverging-neutral: #f0efec;
  --chart-diverging-positive: #e34948;
  --chart-gridline: rgba(0, 0, 0, 0.12);
  --chart-axis: rgba(0, 0, 0, 0.35);
  --chart-sankey-node: #9a9a94; /* default sankey node color */
}
```

Each variable has a built-in light/dark default, so overriding is optional —
only set what you want to brand. Series colors always come from this palette in
series order; no chart type accepts a per-series color override from the API
except Sankey (see [Sankey](#sankey--mires-chart-sankey)).

## Event callbacks

Charts can fire a normalized callback on click or zoom, driven by the API
response rather than by page-side event wiring. Register a named function
before the user interacts with the chart:

```html
<script type="module">
  // window.mires exists once mireswc-charts.js has loaded.
  window.mires.registerChartCallback("onConsentClick", (payload) => {
    // payload: { chartId, chartType, groupingName, event: "click" | "zoom", raw }
    console.log(payload);
  });
</script>
```

The response's `config.event_callbacks` then references that name:

```jsonc
{
  "config": { "event_callbacks": { "click": "onConsentClick" } },
  "groupings": [ /* ... */ ]
}
```

A callback name is only ever resolved against this client-side registry (never
`window[name]` or `eval`), so a server-controlled name can at most reference a
function the host page explicitly registered. Use
`window.mires.unregisterChartCallback(name)` to remove one.

## Chart type reference

Unless noted, a chart type has no chart-specific config and no WebGL variant.

### Line — `<mires-chart-line>`

Simple x/y line chart. One or more series.

```html
<div style="width: 480px; height: 320px;">
  <mires-chart-line data-url="/fixtures/line-single.json"></mires-chart-line>
</div>
```

```jsonc
{
  "groupings": [
    {
      "name": "trend",
      "label": "Trend",
      "labels": { "x_axis_title": "Day", "y_axis_title": "Count" },
      "data": {
        "series": [{ "name": "Consents", "x": [1, 2, 3, 4, 5], "y": [3, 7, 4, 9, 12] }]
      }
    }
  ]
}
```

Has a WebGL variant — see [WebGL rendering](#webgl-rendering).

### Scatter — `<mires-chart-scatter>`

Same Chart Data shape as line (`series[i].x`/`.y`), rendered as unconnected
markers. Multiple groupings show a dropdown automatically:

```jsonc
{
  "groupings": [
    {
      "name": "by_site",
      "label": "By Site",
      "data": {
        "series": [
          { "name": "Site A", "x": [1, 2, 3, 4], "y": [10, 14, 9, 18] },
          { "name": "Site B", "x": [1, 2, 3, 4], "y": [6, 8, 11, 7] }
        ]
      }
    },
    {
      "name": "by_consent_type",
      "label": "By Consent Type",
      "data": { "series": [{ "name": "General", "x": [1, 2, 3, 4], "y": [20, 22, 19, 25] }] }
    }
  ]
}
```

```html
<mires-chart-scatter data-url="/fixtures/scatter-groupings.json"></mires-chart-scatter>
```

Has a WebGL variant.

### Bubble — `<mires-chart-bubble>`

Scatter with a per-point marker size. Same shape as line/scatter, plus `size`:

```jsonc
{
  "groupings": [
    {
      "name": "n",
      "label": "N",
      "data": {
        "series": [
          { "name": "Studies", "x": [1, 2, 3, 4], "y": [5, 9, 4, 12], "size": [10, 30, 15, 40] }
        ]
      }
    }
  ]
}
```

```html
<mires-chart-bubble data-url="/fixtures/bubble.json"></mires-chart-bubble>
```

Has a WebGL variant.

### Filled area — `<mires-chart-filled-area>`

Line chart with the area under the line filled to zero. Same `series[i].x/.y`
shape; a series may set `fill: "none" | "tozeroy" | "tonexty"` to override the
default (`"tozeroy"`).

```jsonc
{
  "groupings": [
    {
      "name": "n",
      "label": "N",
      "data": { "series": [{ "name": "Cumulative", "x": [1, 2, 3, 4, 5], "y": [2, 5, 9, 12, 20] }] }
    }
  ]
}
```

```html
<mires-chart-filled-area data-url="/fixtures/filled-area.json"></mires-chart-filled-area>
```

Has a WebGL variant.

### Bar — `<mires-chart-bar>`

Categorical bar chart. `series[i].values` is positionally aligned with
`categories` — a single series renders a plain bar chart; multiple series
render grouped or stacked bars per `config.bar_mode`.

**Config:** `bar_mode`: `"group"` (default) | `"stack"`. `orientation`: `"v"`
(default) | `"h"`.

```jsonc
// Grouped multi-series bar, horizontal
{
  "config": { "bar_mode": "group", "orientation": "h" },
  "groupings": [
    {
      "name": "n",
      "label": "N",
      "data": {
        "categories": ["Jan", "Feb", "Mar", "Apr"],
        "series": [
          { "name": "Site A", "values": [4, 9, 6, 12] },
          { "name": "Site B", "values": [7, 5, 8, 3] }
        ]
      }
    }
  ]
}
```

```html
<mires-chart-bar data-url="/fixtures/bar-grouped.json"></mires-chart-bar>
```

### Histogram — `<mires-chart-histogram>`

Bins raw values client-side (via plotly.js) rather than taking pre-binned
data — pass the raw per-record numbers in `series[i].values`.

**Config:** `histogram_bins` (chart-wide default binning: `nbinsx`, `start`,
`end`, `size`) — a series' own `bins` overrides it. `orientation`: `"v"`
(default) | `"h"`. `histnorm`: `""` (default, raw counts) | `"percent"` |
`"probability"` | `"density"` | `"probability density"`.

```jsonc
{
  "config": { "histnorm": "percent" },
  "groupings": [
    {
      "name": "n",
      "label": "N",
      "data": {
        "series": [
          { "name": "Ages", "values": [21, 34, 34, 45, 29, 31, 52, 34, 41], "bins": { "size": 5 } }
        ]
      }
    }
  ]
}
```

```html
<mires-chart-histogram data-url="/fixtures/histogram.json"></mires-chart-histogram>
```

### Pie — `<mires-chart-pie>`

Flat shape — no `series` wrapper, since a pie has exactly one distribution per
Chart Grouping. Setting `hole` turns it into a donut; there is no separate
donut element.

**Config:** `hole` (0 default; e.g. `0.4`–`0.7` for a donut). `sort` (default
`true`; `false` preserves array order). `textinfo`: `"label" | "value" |
"percent" | "label+percent" | "label+value" | "value+percent" |
"label+value+percent" | "none"` (default `"label+percent"`).

```jsonc
{
  "config": { "hole": 0.5 },
  "groupings": [
    {
      "name": "n",
      "label": "N",
      "data": {
        "labels": ["Consented", "Declined", "Pending"],
        "values": [62, 9, 14]
      }
    }
  ]
}
```

```html
<mires-chart-pie data-url="/fixtures/pie.json"></mires-chart-pie>
```

### Box — `<mires-chart-box>`

Box plots, one per `boxes[]` entry. A box supplies **either** raw `values`
(plotly computes quartiles client-side) **or** precomputed `stats` — never
both. Boxes sharing the same `group` are drawn as one trace, side-by-side per
category; a box with no `group` falls into the default (ungrouped) trace.

**Box entry fields:** `name`, `group?`, `values?: number[]`, `stats?: { q1,
median, q3, lower_fence?, upper_fence?, mean?, sd? }`.

**Config:** `quartile_method`: `"linear"` (default) | `"exclusive"` |
`"inclusive"` (ignored for boxes using `stats`). `orientation`: `"v"` (default)
| `"h"`.

```jsonc
{
  "groupings": [
    {
      "name": "n",
      "label": "N",
      "data": {
        "boxes": [
          { "name": "Site A", "group": "2024", "values": [12, 15, 14, 18, 21, 13] },
          { "name": "Site B", "group": "2024", "values": [9, 11, 10, 14, 16, 8] },
          { "name": "Site A", "group": "2025", "stats": { "q1": 10, "median": 14, "q3": 19 } }
        ]
      }
    }
  ]
}
```

```html
<mires-chart-box data-url="/fixtures/box.json"></mires-chart-box>
```

### Heatmap — `<mires-chart-heatmap>`

Takes a **pre-binned** matrix `z` — the server has already decided resolution.
`x`/`y` are optional axis labels (default to indices).

**Config:** `color_scale`: `"sequential"` (default, plain magnitude) |
`"diverging"` (for polarity data with a meaningful zero, e.g. a correlation
matrix). `z_mid` (diverging only, default 0).

```jsonc
{
  "config": { "color_scale": "diverging", "z_mid": 0 },
  "groupings": [
    {
      "name": "n",
      "label": "N",
      "data": {
        "z": [
          [1, -0.2, 0.4],
          [-0.2, 1, 0.1],
          [0.4, 0.1, 1]
        ],
        "x": ["Site A", "Site B", "Site C"],
        "y": ["Site A", "Site B", "Site C"]
      }
    }
  ]
}
```

```html
<mires-chart-heatmap data-url="/fixtures/heatmap.json"></mires-chart-heatmap>
```

No WebGL variant (removed from plotly.js in v3.0.0); `webgl-threshold` /
`force-renderer` have no effect.

### 2D density — `<mires-chart-density-2d>`

Like histogram but two-dimensional: `series[i].x`/`.y` are **raw scattered
point pairs**, binned client-side. This is the boundary case with heatmap —
heatmap takes a pre-binned matrix, density takes raw points.

**Config:** `style`: `"heatmap"` (default) | `"contour"`. `density_bins`
(chart-wide default: `nbinsx`, `nbinsy`, `xbins: {start,end,size}`, `ybins:
{...}`) — a series' own `bins` overrides it. Colorscale is always sequential
(no diverging option — density has no polarity concept).

```jsonc
{
  "config": { "style": "contour" },
  "groupings": [
    {
      "name": "n",
      "label": "N",
      "data": {
        "series": [{ "name": "Visits", "x": [1, 2, 2, 3, 3, 3, 4], "y": [5, 4, 6, 5, 6, 7, 6] }]
      }
    }
  ]
}
```

```html
<mires-chart-density-2d data-url="/fixtures/density-2d.json"></mires-chart-density-2d>
```

### Sankey — `<mires-chart-sankey>`

Structurally different from every other type — a nodes+links flow graph, not
x/y or categorical data.

**Data:** `nodes: [{ label, color? }]`, `links: [{ source, target, value,
color? }]` — `source`/`target` are indices into `nodes`. `color` on a node or
link is optional and, unlike every other chart type, **is** honored as a direct
per-item override (the one documented exception to "no per-item color from the
API" — a Sankey's node count is open-ended, so it isn't the fixed small-set
case the categorical palette is designed for). Omitted node colors fall back to
`--chart-sankey-node`; omitted link colors default to a translucent tint of
their source node's color.

**Config:** `orientation`: `"h"` (default) | `"v"`. `arrangement`: `"snap"`
(default) | `"perpendicular"` | `"freeform"` | `"fixed"`.

```jsonc
{
  "groupings": [
    {
      "name": "n",
      "label": "N",
      "data": {
        "nodes": [{ "label": "Invited" }, { "label": "Consented" }, { "label": "Declined" }],
        "links": [
          { "source": 0, "target": 1, "value": 62 },
          { "source": 0, "target": 2, "value": 9 }
        ]
      }
    }
  ]
}
```

```html
<mires-chart-sankey data-url="/fixtures/sankey.json"></mires-chart-sankey>
```

No WebGL variant.

### Mixed-type grid — `<mires-chart-grid>`

Combines several subplots of **different** chart types into one grid layout,
driven by a single combined response — there's no per-subplot Chart Grouping;
one grouping switch (if present) re-renders every subplot together.

**Config:** `rows`, `cols`, and `subplots: [{ type, row, col, config? }]` where
`type` matches another chart element's own type string (`"bar"`,
`"filled-area"`, `"line"`, `"scatter"`, `"bubble"`, `"histogram"`, `"pie"`,
`"box"`, `"heatmap"`, `"density-2d"`, `"sankey"`) and `config` is that
subplot's own chart-specific config (e.g. a `bar` subplot's `config.bar_mode`).

**Data:** `subplots: [...]` — one entry per subplot, **same order** as
`config.subplots`, each shaped per that subplot's own Chart Data (a `bar`
subplot's entry looks like a bar chart's `data`, etc).

```jsonc
{
  "config": {
    "rows": 1,
    "cols": 2,
    "subplots": [
      { "type": "bar", "row": 0, "col": 0, "config": { "bar_mode": "group" } },
      { "type": "pie", "row": 0, "col": 1 }
    ]
  },
  "groupings": [
    {
      "name": "n",
      "label": "N",
      "data": {
        "subplots": [
          { "categories": ["Jan", "Feb"], "series": [{ "name": "Consents", "values": [4, 9] }] },
          { "labels": ["Consented", "Declined"], "values": [62, 9] }
        ]
      }
    }
  ]
}
```

```html
<div style="width: 800px; height: 400px;">
  <mires-chart-grid data-url="/fixtures/grid-mixed.json"></mires-chart-grid>
</div>
```

Notes:

- Pie and Sankey subplots are positioned by `domain` fractions (no shared axis);
  every other subplot type gets its own `xaxis`/`yaxis` pair per grid cell.
- A subplot's `event_callbacks` fire with `chartType` set to that specific
  subplot's `type`, not `"grid"`.
- A WebGL-capable subplot type (line/scatter/bubble/filled-area) inside a grid
  never upgrades to its WebGL variant — `webgl-threshold`/`force-renderer` are
  meaningless here, a known limitation of mixing types in one element.

## WebGL rendering

Line, scatter, bubble, and filled area are the only chart types with a
WebGL-accelerated Plotly trace variant (`scattergl`), used for large point
counts. The decision is:

1. If `force-renderer="svg"` (or `config.force_renderer: "svg"`) — always SVG.
2. If `force-renderer="webgl"` (or `config.force_renderer: "webgl"`) — always WebGL.
3. Otherwise (`"auto"`, the default) — WebGL once the series' total point count
   exceeds `webgl-threshold` (or `config.webgl_threshold`, default 100).

```html
<mires-chart-line
  id="big-line"
  data-url="/fixtures/line-many-points.json"
  webgl-threshold="50"
></mires-chart-line>
```

Every other chart type ignores both attributes — they have no WebGL trace
variant to upgrade to.

## Local development / demo page

`index.html` + `npm run dev` runs a live demo of every chart type against
fixture JSON, without a real backend: a small inline script patches
`window.fetch` to intercept the fixture URLs (e.g. `/fixtures/line-single.json`)
and pass everything else through to the real `fetch`. Look there for more
working examples, including a registered [event callback](#event-callbacks) on
the WebGL-forced line demo.
