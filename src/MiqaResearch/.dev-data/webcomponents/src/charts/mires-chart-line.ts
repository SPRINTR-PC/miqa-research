import { customElement } from "lit/decorators.js";

import { XYChartBase, type XYMode } from "./xy-chart-base.js";

@customElement("mires-chart-line")
export class MiresChartLine extends XYChartBase {
  protected override get mode(): XYMode {
    return "lines";
  }
}
