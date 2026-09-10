import { customElement } from "lit/decorators.js";
import type { Layout } from "plotly.js";

import { MiresChartBase } from "./mires-chart-base.js";
import type { ChartConfig, PlotlyTrace } from "./chart-types.js";

/**
 * Box Chart Data/Config (docs/charts-handoff.md §7.5): boxes sharing a
 * `group` become one trace, side-by-side per category via `boxmode: "group"`
 * — an ungrouped box has no `group` and all such boxes fall into one
 * (unnamed) default trace. Exactly one of `values`/`stats` per entry is
 * enforced server-side; a box supplies raw values (plotly computes quartiles
 * client-side) or precomputed stats, never both.
 */
export interface BoxStats {
  q1: number;
  median: number;
  q3: number;
  lowerFence?: number;
  upperFence?: number;
  mean?: number;
  sd?: number;
}

export interface BoxEntry {
  name: string;
  group?: string;
  values?: number[];
  stats?: BoxStats;
}

export interface BoxChartData {
  boxes: BoxEntry[];
}

export interface BoxChartConfig extends ChartConfig {
  /** Default "linear" — ignored for boxes using precomputed `stats`. */
  quartileMethod?: "linear" | "exclusive" | "inclusive";
  /** Default "v". */
  orientation?: "v" | "h";
}

function groupBy<T>(items: T[], keyOf: (item: T) => string): Record<string, T[]> {
  const groups: Record<string, T[]> = {};
  for (const item of items) {
    const key = keyOf(item);
    (groups[key] ??= []).push(item);
  }
  return groups;
}

export function buildBoxTraces(data: BoxChartData, config?: BoxChartConfig): PlotlyTrace[] {
  const quartilemethod = config?.quartileMethod ?? "linear";
  const orientation = config?.orientation ?? "v";
  const groups = groupBy(data.boxes, (b) => b.group ?? "__default__");

  return Object.entries(groups).map(([groupName, boxes]) => {
    const name = groupName === "__default__" ? undefined : groupName;

    if (boxes.some((b) => b.stats)) {
      const categories = boxes.map((b) => b.name);
      const q1 = boxes.map((b) => b.stats?.q1);
      const median = boxes.map((b) => b.stats?.median);
      const q3 = boxes.map((b) => b.stats?.q3);
      const lowerfence = boxes.map((b) => b.stats?.lowerFence);
      const upperfence = boxes.map((b) => b.stats?.upperFence);
      return {
        type: "box",
        name,
        orientation,
        q1,
        median,
        q3,
        lowerfence,
        upperfence,
        ...(orientation === "v" ? { x: categories } : { y: categories }),
      };
    }

    const categories: string[] = [];
    const values: number[] = [];
    for (const b of boxes) {
      for (const v of b.values ?? []) {
        categories.push(b.name);
        values.push(v);
      }
    }
    return {
      type: "box",
      name,
      orientation,
      quartilemethod,
      ...(orientation === "v" ? { x: categories, y: values } : { x: values, y: categories }),
    };
  });
}

@customElement("mires-chart-box")
export class MiresChartBox extends MiresChartBase<BoxChartData> {
  private get boxConfig(): BoxChartConfig | undefined {
    return this.response?.config as BoxChartConfig | undefined;
  }

  protected override buildTraces(data: BoxChartData): PlotlyTrace[] {
    return buildBoxTraces(data, this.boxConfig).map((trace) => ({
      ...trace,
      type: this.maybeUpgradeTraceType("box", 0), // no-op — box has no WebGL variant (§5)
    }));
  }

  protected override extraLayout(): Partial<Layout> {
    return { boxmode: "group" };
  }
}
