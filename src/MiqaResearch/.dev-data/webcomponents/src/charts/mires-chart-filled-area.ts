import { customElement } from "lit/decorators.js";

import { XYChartBase, type XYMode } from "./xy-chart-base.js";

@customElement("mires-chart-filled-area")
export class MiresChartFilledArea extends XYChartBase {
  protected override get mode(): XYMode {
    return "lines";
  }

  protected override get defaultFill(): "none" | "tozeroy" | "tonexty" {
    return "tozeroy";
  }
}
