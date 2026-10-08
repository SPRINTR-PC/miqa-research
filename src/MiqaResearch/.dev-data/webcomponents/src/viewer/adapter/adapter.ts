// The adapter seam: everything the viewer element needs from a rendering engine.
// The element only ever talks to these types. The Cornerstone3D implementation lives
// in ./cornerstone/ and is loaded lazily; tests inject ./stub.ts instead, so
// vitest/happy-dom (no Worker, no WebGL) never initialises CS3D.
//
// Adding a capability (volume #282, WSI #285, ...): add one member here, implement it
// in its own ./cornerstone/<capability>.ts, and extend the stub.

import type { BulkAnnotationGroup } from "../bulk-annotations.ts";
import type { LayerDisplay } from "../fusion.ts";
import type { Orientation } from "../layout.ts";
import type { DicomJsonInstance, LoadedSeries } from "../series.ts";
import type { Decimation, GpuLimits } from "../size-guard.ts";
import type { SuvStatus } from "../suv.ts";

/** Window as a value range in modality units (e.g. HU after rescale). */
export interface VoiRange {
  lower: number;
  upper: number;
}

/** Observable state of a stack view, rendered by the element and read by browser tests. */
export interface StackState {
  /** 0-based index of the image shown. */
  imageIndex: number;
  imageCount: number;
  voi: VoiRange | undefined;
  /** Tool on the left button (a ToolDef id). */
  activeTool: string;
  invert: boolean;
  /** Camera zoom factor (1 = fit) and pan in canvas pixels. */
  zoom: number;
  pan: [number, number];
  /** CS3D length unit of the image shown, raw (`mm`, `mm Proj`, `px`, …). */
  unit: string;
  /** Annotations (measurements, ROIs, arrows) drawn on this view. */
  annotationCount: number;
  /** A Calibrate line drawn and waiting for its known length (#281). */
  pendingCalibration?: PendingCalibration;
}

/** Calibrate line (#281): its length in the image's current unit. */
export interface PendingCalibration {
  length: number;
  unit: string;
}

/**
 * View-independent controls the chrome drives (tool rail, keys, presets, inspector).
 * Every view kind implements them: stack now, volume (#282) and WSI (#285) later.
 */
export interface ViewControls {
  /** Put a tool (ToolDef id) on the left button; re-applies the workstation mouse bindings. */
  setTool(toolId: string): void;
  setVoi(voi: VoiRange): void;
  /** Back to the image's own window (DICOM default). */
  resetVoi(): void;
  toggleInvert(): void;
  /** Reset camera (zoom/pan) and display properties (window, invert). */
  resetView(): void;
}

export interface StackView extends ViewControls {
  state(): StackState;
  scrollTo(imageIndex: number): void;
  /**
   * User calibration (#281) of the pending Calibrate line's image: the line is `knownLengthMm` long.
   * Planar stacks only; views without calibration (WSI) leave it out.
   */
  calibrate?(knownLengthMm: number): void;
  /** Drop the pending Calibrate line without calibrating. */
  cancelCalibration?(): void;
}

/** One ORTHOGRAPHIC view of a volume (#282). */
export interface VolumeViewState {
  orientation: Orientation;
  /** Camera focal point in world (patient) mm. */
  focalPoint: [number, number, number];
  /** 0-based slice shown along this view's normal. */
  sliceIndex: number;
  sliceCount: number;
}

/** One series shown in a volume view (#284): the base (layers[0]) or a fused overlay. */
export interface LayerState extends LayerDisplay {
  seriesUid: string;
  /** "PT PET AC": modality and description. */
  label: string;
  modality: string;
  /** Window in data units (HU; SUV for PET with SUV applied, else Bq/ml). */
  voi: VoiRange | undefined;
  /** PET only: whether SUV scaling was applied. */
  suv?: SuvStatus;
}

/** Observable state of a volume view: one or three views of one cached volume (plus fused overlays, #284). */
export interface VolumeState {
  activeTool: string;
  /** Window of the selected layer (the base without fusion), the same in every view. */
  voi: VoiRange | undefined;
  invert: boolean;
  /** Slot 0 is the big view. */
  views: VolumeViewState[];
  /** Base first, then overlays in the order fused (#284). */
  layers: LayerState[];
  /** Series UID of the layer that right-drag W/L, presets and setVoi act on. */
  selectedLayer: string;
}

/** Options of `VolumeView.addLayer` (#284). */
export interface LayerOptions {
  /** Initial window, e.g. SUV 0–5; undefined = CS3D's default. */
  voi?: VoiRange;
  /** CS3D's cache refused a slice of the overlay while streaming; the element removes the layer. */
  onTooLarge?: () => void;
}

/** First-render stages a volume reports (#293): coarse interleaved pass done, every slice loaded. */
export type VolumeLoadStage = "interleaved" | "volume-loaded";

export interface VolumeView extends ViewControls {
  state(): VolumeState;
  /** Show the volume in the first `orientations.length` slots (1 or 3), slot 0 = big view. */
  setOrientations(orientations: Orientation[]): Promise<void>;
  /**
   * Fuse `series` into every view (#284), on top of the layers shown. Same Frame of Reference and
   * the budget are checked by the caller (fusion.ts, size guard).
   */
  addLayer(series: LoadedSeries, display: LayerDisplay, options?: LayerOptions): Promise<void>;
  /** Remove an overlay (not the base); the base is selected if it was selected. */
  removeLayer(seriesUid: string): void;
  setLayerDisplay(seriesUid: string, change: Partial<LayerDisplay>): void;
  /** The layer setVoi/resetVoi, presets and right-drag W/L act on. */
  selectLayer(seriesUid: string): void;
}

/** A whole-slide view (#285) with read-only bulk annotations (ANN, #292). */
export interface WsiView extends StackView {
  /** Show ANN instances on the slide through dmv's annotation-group layer (read-only), all groups shown. */
  addBulkAnnotations(instances: DicomJsonInstance[]): Promise<void>;
  bulkAnnotationGroups(): BulkAnnotationGroup[];
  /** Show or hide one group; fires the view's onChange. */
  setBulkAnnotationGroupVisible(uid: string, visible: boolean): void;
}

/** Options of `openVolume`. */
export interface VolumeOptions {
  /**
   * Reduced 3D (#283): load a decimated volume (CS3D `decimatedVolumeLoader` `ijkDecimation`), view only.
   * Undefined = the full-resolution streaming volume.
   */
  decimation?: Decimation;
  /**
   * CS3D's cache refused a slice while streaming (CACHE_SIZE_EXCEEDED, "not cacheable"), after
   * openVolume resolved (#283). The element shows "too large" and goes back to the stack.
   */
  onTooLarge?: () => void;
}

export interface ViewerAdapter {
  /** WebGL2 MAX_3D_TEXTURE_SIZE / MAX_TEXTURE_SIZE, for the size guard (#283). */
  gpuLimits(): GpuLimits;
  /**
   * Show a series as a stack in `element` (a sized, empty div in the element's shadow root).
   * `onChange` fires after every change of the view's StackState (scroll, W/L, first render).
   */
  openStack(element: HTMLDivElement, series: LoadedSeries, onChange: () => void): Promise<StackView>;
  /**
   * Show a whole-slide (WSI) series in `element` (#285). The view is stack-shaped for the chrome:
   * one image, zoom 1 = fit; `scrollTo` is a no-op.
   */
  openWsi(element: HTMLDivElement, series: LoadedSeries, onChange: () => void): Promise<WsiView>;
  /**
   * Show a series as one cached streaming volume in ORTHOGRAPHIC views (#282). `slots` are three
   * empty divs; the first `orientations.length` are visible and sized, and get a view. Only for
   * series that pass the reconstructability rule (../reconstructable.ts).
   */
  openVolume(
    slots: HTMLDivElement[],
    series: LoadedSeries,
    orientations: Orientation[],
    onChange: () => void,
    onStage: (stage: VolumeLoadStage) => void,
    options?: VolumeOptions,
  ): Promise<VolumeView>;
  /**
   * PET (#284): whether SUV scaling was applied to `series` once a view opened it (undefined off PET or
   * before). A missing input falls back to raw Bq/ml silently, so the UI flags it.
   */
  suvStatus(series: LoadedSeries): SuvStatus | undefined;
  /**
   * Drop a series' cached volumes and images (#284: a removed overlay, a replaced series), so the
   * size guard can stop counting them. Call after closing or removing every view showing it.
   */
  evict(seriesUid: string): void;
  /** Release one view opened by this adapter (its viewports and tool group); cached images stay. */
  close(view: ViewControls): void;
  /** Call after the host element changed size; CS3D doesn't observe it. */
  resize(): void;
  /** Release viewports, tool groups and the rendering engine. */
  destroy(): void;
}

export type AdapterFactory = () => Promise<ViewerAdapter>;
