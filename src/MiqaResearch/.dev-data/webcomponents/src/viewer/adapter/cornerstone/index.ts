// The Cornerstone3D ViewerAdapter. Composes one module per capability
// (stack.ts, volume.ts #282; wsi.ts #285, ...). Never imported by vitest.
import { RenderingEngine } from "@cornerstonejs/core";

import type { Orientation } from "../../layout.ts";
import type { LoadedSeries } from "../../series.ts";
import type { GpuLimits } from "../../size-guard.ts";
import type {
  SegmentationView,
  StackView,
  ViewControls,
  ViewerAdapter,
  VolumeLoadStage,
  VolumeOptions,
  VolumeView,
  WsiView,
} from "../adapter.ts";
import { gpuLimits } from "./gpu.ts";
import "./calibration.ts";
import { initCornerstone } from "./init.ts";
import { registerSeriesMetadata } from "./metadata.ts";
import { createSegmentation, type ShownViewports } from "./segmentation.ts";
import { createStackView } from "./stack.ts";
import { createVolumeView } from "./volume.ts";
import { createWsiView } from "./wsi.ts";

let engineCount = 0;

type Handle = ViewControls & { dispose(): void; shownViewports?(): ShownViewports };

class CornerstoneAdapter implements ViewerAdapter {
  private readonly engine = new RenderingEngine(`mires-viewer-${++engineCount}`);
  private readonly views: Handle[] = [];

  gpuLimits(): GpuLimits {
    return gpuLimits();
  }

  async openStack(element: HTMLDivElement, series: LoadedSeries, onChange: () => void): Promise<StackView> {
    const view = await createStackView(this.engine, element, registerSeriesMetadata(series), onChange);
    this.views.push(view);
    return view;
  }

  async openWsi(element: HTMLDivElement, series: LoadedSeries, onChange: () => void): Promise<WsiView> {
    const view = await createWsiView(this.engine, element, series, onChange);
    this.views.push(view);
    return view;
  }

  async openVolume(
    slots: HTMLDivElement[],
    series: LoadedSeries,
    orientations: Orientation[],
    onChange: () => void,
    onStage: (stage: VolumeLoadStage) => void,
    options: VolumeOptions = {},
  ): Promise<VolumeView> {
    const imageIds = registerSeriesMetadata(series);
    // Reduced 3D (#283): in-plane decimation loads `<imageId>#decimation=<i>`; the typed metadata
    // path doesn't strip the fragment, so register those ids too.
    const i = options.decimation?.[0] ?? 1;
    if (i > 1) registerSeriesMetadata({ ...series, images: series.images.map((im) => ({ ...im, imageId: `${im.imageId}#decimation=${i}` })) });
    const view = await createVolumeView(this.engine, slots, imageIds, series.ref.seriesUid, orientations, onChange, onStage, options);
    this.views.push(view);
    return view;
  }

  async openSegmentation(series: LoadedSeries, id: string, onChange: () => void): Promise<SegmentationView> {
    const viewportsOf = (view: ViewControls) => (this.views.includes(view as Handle) ? (view as Handle).shownViewports?.() : undefined);
    return createSegmentation(this.engine, registerSeriesMetadata(series), series, id, onChange, viewportsOf);
  }

  close(view: ViewControls): void {
    const i = this.views.indexOf(view as Handle);
    if (i >= 0) this.views.splice(i, 1)[0].dispose();
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
