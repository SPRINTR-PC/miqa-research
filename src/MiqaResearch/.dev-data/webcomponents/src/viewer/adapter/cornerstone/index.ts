// The Cornerstone3D ViewerAdapter. Composes one module per capability
// (stack.ts now; volume.ts #282, wsi.ts #285, ...). Never imported by vitest.
import { RenderingEngine } from "@cornerstonejs/core";

import type { LoadedSeries } from "../../series.ts";
import type { StackView, ViewerAdapter } from "../adapter.ts";
import "./calibration.ts";
import { initCornerstone } from "./init.ts";
import { registerSeriesMetadata } from "./metadata.ts";
import { createStackView, type StackHandle } from "./stack.ts";
import { createWsiView } from "./wsi.ts";

let engineCount = 0;

class CornerstoneAdapter implements ViewerAdapter {
  private readonly engine = new RenderingEngine(`mires-viewer-${++engineCount}`);
  private readonly views: StackHandle[] = [];

  async openStack(element: HTMLDivElement, series: LoadedSeries, onChange: () => void): Promise<StackView> {
    const view = await createStackView(this.engine, element, registerSeriesMetadata(series), onChange);
    this.views.push(view);
    return view;
  }

  async openWsi(element: HTMLDivElement, series: LoadedSeries, onChange: () => void): Promise<StackView> {
    const view = await createWsiView(this.engine, element, series, onChange);
    this.views.push(view);
    return view;
  }

  resize(): void {
    this.engine.resize(true, true);
  }

  destroy(): void {
    this.views.splice(0).forEach((v) => v.dispose());
    this.engine.destroy();
  }
}

export async function createCornerstoneAdapter(): Promise<ViewerAdapter> {
  await initCornerstone();
  return new CornerstoneAdapter();
}
