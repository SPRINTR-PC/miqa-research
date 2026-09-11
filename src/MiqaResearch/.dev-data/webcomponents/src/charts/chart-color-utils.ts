/**
 * Applies opacity to a resolved color string. Pure string manipulation (no
 * DOM/`getComputedStyle` dependency) so it can run inside a trace-builder
 * pure function (e.g. `buildSankeyTraces`, docs/charts-handoff.md §7.8) —
 * both an API-supplied hex override and `MiresChartBase.resolveThemeColor`'s
 * browser-computed `rgb(...)` output need to work here. Falls back to
 * returning `color` unchanged for any format it doesn't recognize, rather
 * than throwing on unexpected input.
 */
export function withAlpha(color: string, alpha: number): string {
  const trimmed = color.trim();

  const hexMatch = /^#([0-9a-f]{3}|[0-9a-f]{6})$/i.exec(trimmed);
  if (hexMatch) {
    const hex = hexMatch[1];
    const full = hex.length === 3 ? hex.replace(/(.)/g, "$1$1") : hex;
    const r = Number.parseInt(full.slice(0, 2), 16);
    const g = Number.parseInt(full.slice(2, 4), 16);
    const b = Number.parseInt(full.slice(4, 6), 16);
    return `rgba(${r}, ${g}, ${b}, ${alpha})`;
  }

  const rgbMatch = /^rgba?\(\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)(?:\s*,\s*[\d.]+)?\s*\)$/i.exec(trimmed);
  if (rgbMatch) {
    const [, r, g, b] = rgbMatch;
    return `rgba(${r}, ${g}, ${b}, ${alpha})`;
  }

  return color;
}
