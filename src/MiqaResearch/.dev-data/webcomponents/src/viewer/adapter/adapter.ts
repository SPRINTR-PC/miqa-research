// The adapter seam: everything the viewer element needs from a rendering engine.
// The element only ever talks to these types. The Cornerstone3D implementation lives
// in ./cornerstone/ and is loaded lazily; tests inject ./stub.ts instead, so
// vitest/happy-dom (no Worker, no WebGL) never initialises CS3D.
//
// Adding a capability (volume #282, WSI #285, ...): add one member here, implement it
// in its own ./cornerstone/<capability>.ts, and extend the stub.

import type { LoadedSeries } from "../series.ts";

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
}

export interface StackView {
  state(): StackState;
  scrollTo(imageIndex: number): void;
  setVoi(voi: VoiRange): void;
}

export interface ViewerAdapter {
  /**
   * Show a series as a stack in `element` (a sized, empty div in the element's shadow root).
   * `onChange` fires after every change of the view's StackState (scroll, W/L, first render).
   */
  openStack(element: HTMLDivElement, series: LoadedSeries, onChange: () => void): Promise<StackView>;
  /** Call after the host element changed size; CS3D doesn't observe it. */
  resize(): void;
  /** Release viewports, tool groups and the rendering engine. */
  destroy(): void;
}

export type AdapterFactory = () => Promise<ViewerAdapter>;
