import { customElement } from "lit/decorators.js";

import { withAlpha } from "./chart-color-utils.js";
import { MiresChartBase } from "./mires-chart-base.js";
import type { ChartConfig, PlotlyTrace } from "./chart-types.js";

/**
 * Sankey Chart Data/Config (docs/charts-handoff.md §7.8): structurally
 * different from every other chart type — a nodes+links graph, not x/y or
 * categorical. `SankeyNode.color`/`SankeyLink.color` are the one documented
 * exception (ADR 0022 amendment) to the "no per-item color override" policy
 * every other type follows: a Sankey's node count is open-ended, so per-node
 * identity was never the small-fixed-set case the categorical palette
 * protects.
 */
export interface SankeyNode {
  label: string;
  /** Explicit override; defaults to a neutral tone when omitted. */
  color?: string;
}

export interface SankeyLink {
  source: number;
  target: number;
  value: number;
  /** Explicit override; defaults to a translucent tint of the source node's color. */
  color?: string;
}

export interface SankeyChartData {
  nodes: SankeyNode[];
  links: SankeyLink[];
}

export interface SankeyChartConfig extends ChartConfig {
  /** Default "h". */
  orientation?: "h" | "v";
  /** Default "snap". */
  arrangement?: "snap" | "perpendicular" | "freeform" | "fixed";
}

export function buildSankeyTraces(
  data: SankeyChartData,
  config: SankeyChartConfig | undefined,
  defaultNodeColor: string,
): PlotlyTrace[] {
  const nodeColors = data.nodes.map((n) => n.color ?? defaultNodeColor);
  const linkColors = data.links.map((l) => l.color ?? withAlpha(nodeColors[l.source] ?? defaultNodeColor, 0.4));

  return [
    {
      type: "sankey",
      orientation: config?.orientation ?? "h",
      arrangement: config?.arrangement ?? "snap",
      node: {
        label: data.nodes.map((n) => n.label),
        color: nodeColors,
      },
      link: {
        source: data.links.map((l) => l.source),
        target: data.links.map((l) => l.target),
        value: data.links.map((l) => l.value),
        color: linkColors,
      },
    },
  ];
}

@customElement("mires-chart-sankey")
export class MiresChartSankey extends MiresChartBase<SankeyChartData> {
  private get sankeyConfig(): SankeyChartConfig | undefined {
    return this.response?.config as SankeyChartConfig | undefined;
  }

  /**
   * No `maybeUpgradeTraceType` call here — unlike every other no-op type
   * (pie, heatmap, ...), Sankey has no WebGL-accelerated trace variant at
   * all, not even routed through the shared upgrade mechanism as a
   * documented no-op (§5/§7.8).
   */
  protected override buildTraces(data: SankeyChartData): PlotlyTrace[] {
    return buildSankeyTraces(data, this.sankeyConfig, this.resolveThemeColor("--mires-chart-sankey-node"));
  }
}
