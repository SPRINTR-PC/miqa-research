import type { ChartCallback } from "./chart-types.js";

/**
 * Chart Event Callback registry (CONTEXT.md, ADR 0021). A chart resolves the
 * function named in `config.eventCallbacks.click`/`.zoom` against this
 * client-side registry only — never a raw `window[name]` lookup or `eval` —
 * so a server-supplied name can at most reference an unregistered no-op or a
 * function the host page already explicitly chose to expose.
 */
const registry = new Map<string, ChartCallback>();

export function registerChartCallback(name: string, fn: ChartCallback): void {
  registry.set(name, fn);
}

export function unregisterChartCallback(name: string): void {
  registry.delete(name);
}

/**
 * Resolution is lazy — call this only at the moment an event actually fires,
 * never at connect-time or fetch-time, so the host page only needs to
 * register a name before the user interacts, not before the chart renders.
 */
export function resolveChartCallback(name: string): ChartCallback | undefined {
  return registry.get(name);
}

declare global {
  interface Window {
    mires?: {
      registerChartCallback?: typeof registerChartCallback;
      unregisterChartCallback?: typeof unregisterChartCallback;
    };
  }
}

if (typeof window !== "undefined") {
  window.mires = window.mires ?? {};
  window.mires.registerChartCallback = registerChartCallback;
  window.mires.unregisterChartCallback = unregisterChartCallback;
}
