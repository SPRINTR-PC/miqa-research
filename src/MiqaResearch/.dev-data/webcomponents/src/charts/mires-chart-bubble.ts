import { customElement } from "lit/decorators.js";

import { XYChartBase, type XYMode } from "./xy-chart-base.js";

/** Expects each series in its Chart Data to set `size` (marker size per point). */
@customElement("mires-chart-bubble")
export class MiresChartBubble extends XYChartBase {
  protected override get mode(): XYMode {
    return "markers";
  }
}
