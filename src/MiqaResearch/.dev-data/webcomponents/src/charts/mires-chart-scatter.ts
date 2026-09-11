import { customElement } from "lit/decorators.js";

import { XYChartBase, type XYMode } from "./xy-chart-base.js";

@customElement("mires-chart-scatter")
export class MiresChartScatter extends XYChartBase {
  protected override get mode(): XYMode {
    return "markers";
  }
}
