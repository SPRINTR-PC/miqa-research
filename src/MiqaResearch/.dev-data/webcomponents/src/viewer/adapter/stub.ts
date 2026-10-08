// In-memory ViewerAdapter for vitest: records calls and lets a test drive state changes.
import { annotationGroups, type BulkAnnotationGroup } from "../bulk-annotations.ts";
import { layerDisplay, modalityOf, seriesLabel, type LayerDisplay } from "../fusion.ts";
import type { Orientation } from "../layout.ts";
import type { DicomJsonInstance, LoadedSeries } from "../series.ts";
import { DEFAULT_BRUSH_SIZE, SegmentList, type Rgb, type SegmentationState, type ValueRange } from "../segmentation.ts";
import type { GpuLimits } from "../size-guard.ts";
import { suvStatusFor, type SuvStatus } from "../suv.ts";
import type {
  SegmentationView,
  LayerOptions,
  LayerState,
  StackState,
  ThresholdOptions,
  StackView,
  ViewControls,
  ViewerAdapter,
  VoiRange,
  VolumeLoadStage,
  VolumeState,
  VolumeOptions,
  VolumeView,
  WsiView,
} from "./adapter.ts";

export class StubStackView implements StackView {
  current: StackState;
  /** Window the image came with; resetVoi/resetView go back to it. */
  defaultVoi: VoiRange | undefined;
  resets = 0;
  /** Known lengths passed to calibrate(). */
  calibrations: number[] = [];
  private readonly onChange: () => void;

  constructor(series: LoadedSeries, onChange: () => void) {
    this.current = {
      imageIndex: 0,
      imageCount: series.images.length,
      voi: undefined,
      activeTool: "",
      invert: false,
      zoom: 1,
      pan: [0, 0],
      unit: "mm",
      annotationCount: 0,
    };
    this.onChange = onChange;
  }

  state(): StackState {
    return { ...this.current };
  }

  /** Test helper: apply a partial state change as the engine would, and notify. */
  emit(change: Partial<StackState>): void {
    Object.assign(this.current, change);
    this.onChange();
  }

  scrollTo(imageIndex: number): void {
    this.emit({ imageIndex: Math.max(0, Math.min(imageIndex, this.current.imageCount - 1)) });
  }

  setVoi(voi: VoiRange): void {
    this.emit({ voi });
  }

  resetVoi(): void {
    this.emit({ voi: this.defaultVoi });
  }

  setTool(toolId: string): void {
    this.emit({ activeTool: toolId });
  }

  toggleInvert(): void {
    this.emit({ invert: !this.current.invert });
  }

  calibrate(knownLengthMm: number): void {
    this.calibrations.push(knownLengthMm);
    this.emit({ unit: "mm User", pendingCalibration: undefined });
  }

  cancelCalibration(): void {
    this.emit({ pendingCalibration: undefined });
  }

  resetView(): void {
    this.resets += 1;
    this.emit({ voi: this.defaultVoi, invert: false, zoom: 1, pan: [0, 0] });
  }
}

/** A slide view: one image, plus ANN groups held in memory. */
export class StubWsiView extends StubStackView implements WsiView {
  bulkInstances: DicomJsonInstance[] = [];
  private groups: BulkAnnotationGroup[] = [];

  async addBulkAnnotations(instances: DicomJsonInstance[]): Promise<void> {
    this.bulkInstances.push(...instances);
    this.groups.push(...annotationGroups(instances));
    this.emit({});
  }

  bulkAnnotationGroups(): BulkAnnotationGroup[] {
    return this.groups.map((g) => ({ ...g }));
  }

  setBulkAnnotationGroupVisible(uid: string, visible: boolean): void {
    this.groups = this.groups.map((g) => (g.uid === uid ? { ...g, visible } : g));
    this.emit({});
  }
}

export class StubVolumeView implements VolumeView {
  current: VolumeState;
  orientations: Orientation[];
  readonly slots: HTMLDivElement[];
  readonly series: LoadedSeries;
  /** Options openVolume was called with (#283 decimation). */
  options: VolumeOptions | undefined;
  private readonly onChange: () => void;
  private readonly onStage: (stage: VolumeLoadStage) => void;

  constructor(
    slots: HTMLDivElement[],
    series: LoadedSeries,
    orientations: Orientation[],
    onChange: () => void,
    onStage: (stage: VolumeLoadStage) => void,
  ) {
    this.slots = slots;
    this.series = series;
    this.orientations = orientations;
    this.onChange = onChange;
    this.onStage = onStage;
    const base: LayerState = {
      seriesUid: series.ref.seriesUid,
      label: seriesLabel(series),
      modality: modalityOf(series),
      voi: undefined,
      ...layerDisplay(modalityOf(series), { base: true }),
      ...(suvStatusFor(series) ? { suv: suvStatusFor(series) } : {}),
    };
    this.current = { activeTool: "", voi: undefined, invert: false, views: this.viewStates(), layers: [base], selectedLayer: base.seriesUid };
  }

  /** Fused overlays (#284): series fused with their options, for tests. */
  layerOptions = new Map<string, LayerOptions | undefined>();

  /** Base window lives in `current.voi`; overlays keep their own. */
  private layerStates(): LayerState[] {
    return this.current.layers.map((l, i) => ({ ...l, curve: l.curve.map((p) => ({ ...p })), voi: i === 0 ? this.current.voi : l.voi }));
  }

  private viewStates() {
    const n = this.series.images.length;
    return this.orientations.map((orientation) => ({
      orientation,
      focalPoint: [0, 0, 0] as [number, number, number],
      sliceIndex: Math.floor(n / 2),
      sliceCount: n,
    }));
  }

  state(): VolumeState {
    const layers = this.layerStates();
    const voi = layers.find((l) => l.seriesUid === this.current.selectedLayer)?.voi;
    return { ...this.current, voi, views: this.current.views.map((v) => ({ ...v })), layers };
  }

  private get selectedIsBase(): boolean {
    return this.current.selectedLayer === this.current.layers[0].seriesUid;
  }

  private updateLayer(uid: string, change: Partial<LayerState>): void {
    this.emit({ layers: this.current.layers.map((l) => (l.seriesUid === uid ? { ...l, ...change } : l)) });
  }

  async addLayer(series: LoadedSeries, display: LayerDisplay, options?: LayerOptions): Promise<void> {
    const suv: SuvStatus | undefined = suvStatusFor(series);
    const layer: LayerState = {
      seriesUid: series.ref.seriesUid,
      label: seriesLabel(series),
      modality: modalityOf(series),
      voi: options?.voi,
      ...display,
      curve: display.curve.map((p) => ({ ...p })),
      ...(suv ? { suv } : {}),
    };
    this.layerOptions.set(layer.seriesUid, options);
    this.emit({ layers: [...this.current.layers, layer] });
  }

  removeLayer(seriesUid: string): void {
    if (seriesUid === this.current.layers[0].seriesUid) return;
    const selectedLayer = this.current.selectedLayer === seriesUid ? this.current.layers[0].seriesUid : this.current.selectedLayer;
    this.emit({ layers: this.current.layers.filter((l) => l.seriesUid !== seriesUid), selectedLayer });
  }

  setLayerDisplay(seriesUid: string, change: Partial<LayerDisplay>): void {
    this.updateLayer(seriesUid, change);
  }

  selectLayer(seriesUid: string): void {
    if (this.current.layers.some((l) => l.seriesUid === seriesUid)) this.emit({ selectedLayer: seriesUid });
  }

  /** Test helper: CS3D's cache refused a slice of an overlay while streaming. */
  overlayTooLarge(seriesUid: string): void {
    this.layerOptions.get(seriesUid)?.onTooLarge?.();
  }

  emit(change: Partial<VolumeState>): void {
    Object.assign(this.current, change);
    this.onChange();
  }

  /** Test helper: CS3D's cache refused a slice while streaming (#283). */
  tooLarge(): void {
    this.options?.onTooLarge?.();
  }

  /** Test helper: report a first-render stage as the engine would. */
  stage(stage: VolumeLoadStage): void {
    this.onStage(stage);
  }

  async setOrientations(orientations: Orientation[]): Promise<void> {
    this.orientations = [...orientations];
    this.emit({ views: this.viewStates() });
  }

  setTool(toolId: string): void {
    this.emit({ activeTool: toolId });
  }

  setVoi(voi: VoiRange): void {
    if (this.selectedIsBase) this.emit({ voi });
    else this.updateLayer(this.current.selectedLayer, { voi });
  }

  resetVoi(): void {
    if (this.selectedIsBase) this.emit({ voi: undefined });
    else this.updateLayer(this.current.selectedLayer, { voi: this.layerOptions.get(this.current.selectedLayer)?.voi });
  }

  toggleInvert(): void {
    this.emit({ invert: !this.current.invert });
  }

  resetView(): void {
    this.emit({ voi: undefined, invert: false });
  }
}

/** A Segmentation held in memory (#286): the segment list, the views it was shown in, threshold calls. */
export class StubSegmentationView implements SegmentationView {
  readonly id: string;
  readonly series: LoadedSeries;
  readonly list = new SegmentList();
  brushSize = DEFAULT_BRUSH_SIZE;
  /** Test-controlled: rectangles drawn, voxels per segment, voxels the next threshold sets. */
  thresholdRectangles = 0;
  voxels: Record<number, number> = {};
  thresholdResult = 0;
  shownIn: ViewControls[] = [];
  thresholds: { range: ValueRange; options: ThresholdOptions }[] = [];
  closed = false;
  private readonly onChange: () => void;

  constructor(series: LoadedSeries, id: string, onChange: () => void) {
    this.series = series;
    this.id = id;
    this.onChange = onChange;
  }

  state(): SegmentationState {
    return {
      segments: this.list.segments.map((s) => ({ ...s, color: [...s.color] as Rgb })),
      active: this.list.active,
      brushSize: this.brushSize,
      thresholdRectangles: this.thresholdRectangles,
    };
  }

  /** Test helper: change state as the engine would (e.g. a rectangle drawn), and notify. */
  emit(change: Partial<Pick<StubSegmentationView, "thresholdRectangles" | "voxels">> = {}): void {
    Object.assign(this, change);
    this.onChange();
  }

  async show(view: ViewControls): Promise<void> {
    this.shownIn.push(view);
  }

  addSegment(): void {
    this.list.add();
    this.onChange();
  }

  renameSegment(index: number, label: string): void {
    this.list.rename(index, label);
    this.onChange();
  }

  setSegmentColor(index: number, color: Rgb): void {
    this.list.setColor(index, color);
    this.onChange();
  }

  setActiveSegment(index: number): void {
    this.list.setActive(index);
    this.onChange();
  }

  setBrushSize(size: number): void {
    this.brushSize = size;
    this.onChange();
  }

  threshold(range: ValueRange, options: ThresholdOptions): number {
    this.thresholds.push({ range, options });
    if (!this.thresholdRectangles) return 0;
    const active = this.list.active;
    this.voxels = { ...this.voxels, [active]: (this.voxels[active] ?? 0) + this.thresholdResult };
    this.emit({ thresholdRectangles: 0 });
    return this.thresholdResult;
  }

  voxelCounts(): Record<number, number> {
    return { ...this.voxels };
  }

  close(): void {
    this.closed = true;
  }
}

export class StubAdapter implements ViewerAdapter {
  opened: { element: HTMLDivElement; series: LoadedSeries }[] = [];
  openedWsi: { element: HTMLDivElement; series: LoadedSeries }[] = [];
  views: StubStackView[] = [];
  wsiViews: StubWsiView[] = [];
  volumes: StubVolumeView[] = [];
  closed: ViewControls[] = [];
  resizes = 0;
  destroyed = false;
  /** Set to make the next openStack reject. */
  failWith: Error | undefined;
  /** Set to make the next openVolume reject (e.g. CS3D's CACHE_SIZE_EXCEEDED, #283). */
  volumeFailWith: Error | undefined;
  /** Segmentations opened (#286). */
  segmentations: StubSegmentationView[] = [];
  /** Set to make the next openSegmentation reject (e.g. CS3D's "not cacheable"). */
  segmentationFailWith: Error | undefined;
  /** GPU limits reported to the size guard (#283); a typical desktop by default. */
  gpu: GpuLimits = { max3dTextureSize: 2048, maxTextureSize: 16384 };

  gpuLimits(): GpuLimits {
    return this.gpu;
  }

  async openStack(element: HTMLDivElement, series: LoadedSeries, onChange: () => void): Promise<StackView> {
    if (this.failWith) throw this.failWith;
    this.opened.push({ element, series });
    const view = new StubStackView(series, onChange);
    this.views.push(view);
    return view;
  }

  async openWsi(element: HTMLDivElement, series: LoadedSeries, onChange: () => void): Promise<WsiView> {
    if (this.failWith) throw this.failWith;
    this.openedWsi.push({ element, series });
    const view = new StubWsiView({ ...series, images: series.images.slice(0, 1) }, onChange);
    this.views.push(view);
    this.wsiViews.push(view);
    return view;
  }

  async openVolume(
    slots: HTMLDivElement[],
    series: LoadedSeries,
    orientations: Orientation[],
    onChange: () => void,
    onStage: (stage: VolumeLoadStage) => void,
    options?: VolumeOptions,
  ): Promise<VolumeView> {
    if (this.failWith) throw this.failWith;
    const fail = this.volumeFailWith;
    this.volumeFailWith = undefined;
    if (fail) throw fail;
    const view = new StubVolumeView(slots, series, [...orientations], onChange, onStage);
    view.options = options;
    this.volumes.push(view);
    return view;
  }

  async openSegmentation(series: LoadedSeries, id: string, onChange: () => void): Promise<SegmentationView> {
    const fail = this.segmentationFailWith;
    this.segmentationFailWith = undefined;
    if (fail) throw fail;
    const seg = new StubSegmentationView(series, id, onChange);
    this.segmentations.push(seg);
    return seg;
  }

  /** Series evicted from the cache (#284). */
  evicted: string[] = [];

  evict(seriesUid: string): void {
    this.evicted.push(seriesUid);
  }

  suvStatus(series: LoadedSeries): SuvStatus | undefined {
    return suvStatusFor(series);
  }

  close(view: ViewControls): void {
    this.closed.push(view);
  }

  resize(): void {
    this.resizes += 1;
  }

  destroy(): void {
    this.destroyed = true;
  }
}
