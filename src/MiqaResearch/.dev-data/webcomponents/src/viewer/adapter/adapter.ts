// The adapter seam: everything the viewer element needs from a rendering engine.
// The element only ever talks to these types. The Cornerstone3D implementation lives
// in ./cornerstone/ and is loaded lazily; tests inject ./stub.ts instead, so
// vitest/happy-dom (no Worker, no WebGL) never initialises CS3D.
//
// Adding a capability (volume #282, WSI #285, ...): add one member here, implement it
// in its own ./cornerstone/<capability>.ts, and extend the stub.

import type { BulkAnnotationGroup } from "../bulk-annotations.ts";
import type { Orientation } from "../layout.ts";
import type { DicomJsonInstance, LoadedSeries } from "../series.ts";
import type { Rgb, SegmentationState, ValueRange } from "../segmentation.ts";
import type { Decimation, GpuLimits } from "../size-guard.ts";

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

/** Observable state of a volume view: one or three views of one cached volume. */
export interface VolumeState {
  activeTool: string;
  /** Window of the base volume (the same in every view). */
  voi: VoiRange | undefined;
  invert: boolean;
  /** Slot 0 is the big view. */
  views: VolumeViewState[];
}

/** First-render stages a volume reports (#293): coarse interleaved pass done, every slice loaded. */
export type VolumeLoadStage = "interleaved" | "volume-loaded";

export interface VolumeView extends ViewControls {
  state(): VolumeState;
  /** Show the volume in the first `orientations.length` slots (1 or 3), slot 0 = big view. */
  setOrientations(orientations: Orientation[]): Promise<void>;
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

/** Options of `SegmentationView.threshold`. */
export interface ThresholdOptions {
  /** Also fill this many slices before and after the rectangle's (0 = its slice only). */
  slices: number;
  /**
   * Series whose values are thresholded on a volume: the selected layer (#284); default the base
   * series. A stack thresholds its own images.
   */
  sourceSeriesUid?: string;
}

/**
 * A Segmentation (#286): one labelmap on the base series' grid (one labelmap image per image),
 * shown in whichever stack or volume view is open. Segment tools paint its active segment.
 */
export interface SegmentationView {
  /** CS3D segmentation id, also its size-guard budget entry id. */
  readonly id: string;
  state(): SegmentationState;
  /** Show the labelmap in `view` and make it the active one there; call after every open or re-layout. */
  show(view: ViewControls): Promise<void>;
  addSegment(): void;
  renameSegment(index: number, label: string): void;
  setSegmentColor(index: number, color: Rgb): void;
  setActiveSegment(index: number): void;
  setBrushSize(size: number): void;
  /**
   * Fill the active segment where the values are within `range`, inside the drawn Rectangle ROI
   * threshold rectangles, which are then removed. Returns the voxels newly in the segment.
   */
  threshold(range: ValueRange, options: ThresholdOptions): number;
  /** Labelled voxels per segment index (painted ones only). */
  voxelCounts(): Record<number, number>;
  /** Bumps on every edit (painting, threshold, polygon fill, segment added / renamed / recoloured) (#289). */
  revision(): number;
  /** SEG 66.4 BINARY (DICOM Part 10) of the painted segments (#289). Throws when nothing is painted. */
  exportSeg(): Promise<Blob>;
  /** Drop the labelmap and its cached images. */
  close(): void;
}

/**
 * The annotations (measurements, ROIs, arrows) drawn in the adapter's views (#289): CS3D keeps one
 * annotation state for every view, so this is per adapter, not per view. Calibrate lines and the
 * segment tools' helper annotations aren't annotations here.
 */
export interface AnnotationSet {
  /** Bumps on every annotation completed, changed or removed, and on every User calibration. */
  revision(): number;
  /** Annotations on `series` (its images, or its volume). */
  count(series: LoadedSeries): number;
  /** Tool names of the annotations on `series` (Save warns about those the SR can't hold). */
  toolNames(series: LoadedSeries): string[];
  /**
   * SR TID 1500 (Comprehensive 3D SR, DICOM Part 10) of the annotations on `series`, built with
   * `@cornerstonejs/adapters`: true UCUM units, the calibration type qualifier, User calibrations
   * (../sr.ts). On WSI: SCOORD3D in slide mm, freehand contours simplified, geometric measurements only.
   */
  exportSr(series: LoadedSeries): Promise<Blob>;
  /** Remove the annotations on `series`. */
  clear(series: LoadedSeries): void;
  /** Show the annotations of an SR (a served DICOM JSON instance) on `series`, reapplying its User calibrations. */
  importSr(instance: DicomJsonInstance, series: LoadedSeries): Promise<void>;
  /** Stop listening to CS3D. */
  dispose(): void;
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
   * Create a Segmentation on `series`' grid (#286), "Segment 1" active. Check the size guard first;
   * CS3D cache errors are thrown (`isTooLargeError`). `onChange` fires after every change of its state or voxels.
   */
  openSegmentation(series: LoadedSeries, id: string, onChange: () => void): Promise<SegmentationView>;
  /** The annotations of every view (#289); `onChange` fires when `revision()` bumps. Call once. */
  watchAnnotations(onChange: () => void): AnnotationSet;
  /** Release one view opened by this adapter (its viewports and tool group); cached images stay. */
  close(view: ViewControls): void;
  /** Call after the host element changed size; CS3D doesn't observe it. */
  resize(): void;
  /** Release viewports, tool groups and the rendering engine. */
  destroy(): void;
}

export type AdapterFactory = () => Promise<ViewerAdapter>;
