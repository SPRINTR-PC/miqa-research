import { css } from "lit";

/**
 * Chart Palette (CONTEXT.md, ADR 0022): the color system every chart component
 * resolves via `getComputedStyle` at render time. Categorical colors are the
 * `dataviz` skill's own validated 8-hue default, fixed and NOT derived from
 * `--mires-color-primary-parts`/`--mires-color-secondary-parts` — a brand-anchored
 * reorder was tried and failed the skill's colorblind-safety validator in dark
 * mode. The sequential ramp is computed live from the primary brand hue via CSS
 * relative-color syntax, since a single-hue lightness ramp carries no cross-hue
 * CVD risk (unlike the categorical set).
 *
 * A chart element mirrors `document.documentElement`'s `data-theme` attribute
 * onto itself (see MiresChartBase) so `:host([data-theme="dark"])` below can
 * react to an explicit theme toggle even when the surrounding page has no dark
 * theme of its own yet.
 *
 * The diverging ramp (negative/neutral/positive, ADR 0022 amendment from #82)
 * is likewise fixed rather than brand-derived, and — like the categorical set
 * — has distinct light/dark hex values rather than being computed live: its
 * poles reuse the categorical set's blue (slot 1) and red (slot 8) hues, with
 * a neutral gray midpoint, per the `dataviz` skill's diverging-pair guidance.
 *
 * `--mires-chart-sankey-node` (added by #84) is the neutral tone a Sankey
 * node falls back to when its `SankeyNode.color` override is omitted — the
 * one chart type where the API may set an arbitrary per-item color at all
 * (ADR 0022 amendment), so unlike the categorical/sequential/diverging sets
 * above it's a single fallback color, not a ramp.
 */
export const chartPaletteStyles = css`
  :host {
    /* Chart Palette — categorical (light) */
    --mires-chart-series-1: var(--chart-series-1, #2a78d6);
    --mires-chart-series-2: var(--chart-series-2, #eb6834);
    --mires-chart-series-3: var(--chart-series-3, #1baf7a);
    --mires-chart-series-4: var(--chart-series-4, #eda100);
    --mires-chart-series-5: var(--chart-series-5, #e87ba4);
    --mires-chart-series-6: var(--chart-series-6, #008300);
    --mires-chart-series-7: var(--chart-series-7, #4a3aa7);
    --mires-chart-series-8: var(--chart-series-8, #e34948);

    /* Chart Palette — sequential (computed live from the primary brand hue) */
    --mires-chart-sequential-0: var(--chart-sequential-0, hsl(from var(--mires-color-primary-parts) h s 95%));
    --mires-chart-sequential-1: var(--chart-sequential-1, hsl(from var(--mires-color-primary-parts) h s 80%));
    --mires-chart-sequential-2: var(--chart-sequential-2, hsl(from var(--mires-color-primary-parts) h s 65%));
    --mires-chart-sequential-3: var(--chart-sequential-3, hsl(from var(--mires-color-primary-parts) h s 50%));
    --mires-chart-sequential-4: var(--chart-sequential-4, hsl(from var(--mires-color-primary-parts) h s 35%));
    --mires-chart-sequential-5: var(--chart-sequential-5, hsl(from var(--mires-color-primary-parts) h s 20%));

    /* Chart Palette — diverging (fixed blue/gray/red, ADR 0022 amendment) */
    --mires-chart-diverging-negative: var(--chart-diverging-negative, #2a78d6);
    --mires-chart-diverging-neutral: var(--chart-diverging-neutral, #f0efec);
    --mires-chart-diverging-positive: var(--chart-diverging-positive, #e34948);

    /* Chart Palette — gridlines / axis, derived from the existing text color */
    --mires-chart-gridline: var(--chart-gridline, hsl(from var(--mires-color-text-parts) h s l / 0.12));
    --mires-chart-axis: var(--chart-axis, hsl(from var(--mires-color-text-parts) h s l / 0.35));

    /* Chart Palette — sankey node default (neutral tone, ADR 0022 amendment) */
    --mires-chart-sankey-node: var(--chart-sankey-node, #9a9a94);
  }

  @media (prefers-color-scheme: dark) {
    :host(:not([data-theme="light"])) {
      --mires-chart-series-1: var(--chart-series-1, #3987e5);
      --mires-chart-series-2: var(--chart-series-2, #d95926);
      --mires-chart-series-3: var(--chart-series-3, #199e70);
      --mires-chart-series-4: var(--chart-series-4, #c98500);
      --mires-chart-series-5: var(--chart-series-5, #d55181);
      --mires-chart-series-6: var(--chart-series-6, #008300);
      --mires-chart-series-7: var(--chart-series-7, #9085e9);
      --mires-chart-series-8: var(--chart-series-8, #e66767);

      --mires-chart-diverging-negative: var(--chart-diverging-negative, #3987e5);
      --mires-chart-diverging-neutral: var(--chart-diverging-neutral, #383835);
      --mires-chart-diverging-positive: var(--chart-diverging-positive, #e66767);

      --mires-chart-sankey-node: var(--chart-sankey-node, #6f6f68);
    }
  }

  :host([data-theme="dark"]) {
    --mires-chart-series-1: var(--chart-series-1, #3987e5);
    --mires-chart-series-2: var(--chart-series-2, #d95926);
    --mires-chart-series-3: var(--chart-series-3, #199e70);
    --mires-chart-series-4: var(--chart-series-4, #c98500);
    --mires-chart-series-5: var(--chart-series-5, #d55181);
    --mires-chart-series-6: var(--chart-series-6, #008300);
    --mires-chart-series-7: var(--chart-series-7, #9085e9);
    --mires-chart-series-8: var(--chart-series-8, #e66767);

    --mires-chart-diverging-negative: var(--chart-diverging-negative, #3987e5);
    --mires-chart-diverging-neutral: var(--chart-diverging-neutral, #383835);
    --mires-chart-diverging-positive: var(--chart-diverging-positive, #e66767);

    --mires-chart-sankey-node: var(--chart-sankey-node, #6f6f68);
  }
`;
