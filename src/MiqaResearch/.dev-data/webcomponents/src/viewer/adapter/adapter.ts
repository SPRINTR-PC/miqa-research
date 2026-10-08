// The adapter seam: everything the viewer element needs from a rendering engine.
// The element only ever talks to these types. The Cornerstone3D implementation lives
// in ./cornerstone/ and is loaded lazily; tests inject ./stub.ts instead, so
// vitest/happy-dom (no Worker, no WebGL) never initialises CS3D.
//
// Adding a capability (volume #282, WSI #285, ...): add one member here, implement it
// in its own ./cornerstone/<capability>.ts, and extend the stub.

import type { BulkAnnotationGroup } from "../bulk-annotations.ts";
import type { DicomJsonInstance, LoadedSeries } from "../series.ts";

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
}

/** A whole-slide view (#285) with read-only bulk annotations (ANN, #292). */
export interface WsiView extends StackView {
  /** Show ANN instances on the slide through dmv's annotation-group layer (read-only), all groups shown. */
  addBulkAnnotations(instances: DicomJsonInstance[]): Promise<void>;
  bulkAnnotationGroups(): BulkAnnotationGroup[];
  /** Show or hide one group; fires the view's onChange. */
  setBulkAnnotationGroupVisible(uid: string, visible: boolean): void;
}

export interface ViewerAdapter {
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
  /** Call after the host element changed size; CS3D doesn't observe it. */
  resize(): void;
  /** Release viewports, tool groups and the rendering engine. */
  destroy(): void;
}

export type AdapterFactory = () => Promise<ViewerAdapter>;
