// Volume layouts (spec #271 "Three views", #282). Pure, no CS3D.
//   1×1: one orientation, V cycles it. 1×3: big view left, the other two stacked on the right;
//   draggable split (25–85%, default 66%, remembered per browser); double-click swaps into the big view.

import type { Decimation } from "./size-guard.ts";

export type Orientation = "axial" | "sagittal" | "coronal";

export const ORIENTATIONS: readonly Orientation[] = ["axial", "sagittal", "coronal"];

/**
 * What the viewport area shows: the acquired stack, or a volume in one or three views (slot 0 = big view).
 * `reduced` (#283): a decimated, view-only volume for a series too big for full-resolution 3D.
 */
export type ViewLayout = { kind: "stack" } | { kind: "volume"; orientations: Orientation[]; reduced?: Decimation };

/** Crosshair line and view frame colour per orientation (CS3D crosshairs example colours). */
export const ORIENTATION_COLOR: Record<Orientation, string> = {
  axial: "rgb(200, 0, 0)",
  sagittal: "rgb(200, 200, 0)",
  coronal: "rgb(0, 200, 0)",
};

export function cycleOrientation(o: Orientation): Orientation {
  return ORIENTATIONS[(ORIENTATIONS.indexOf(o) + 1) % ORIENTATIONS.length];
}

/** Three views with `main` in the big one, the others in the canonical order. */
export function threeViews(main: Orientation): Orientation[] {
  return [main, ...ORIENTATIONS.filter((o) => o !== main)];
}

export function swapIntoMain(orientations: Orientation[], slot: number): Orientation[] {
  const next = [...orientations];
  [next[0], next[slot]] = [next[slot], next[0]];
  return next;
}

export const DEFAULT_SPLIT = 66;
export const SPLIT_STORAGE_KEY = "mires-viewer-split";

export function clampSplit(percent: number): number {
  return Math.round(Math.min(85, Math.max(25, percent)));
}

/** Split of the big view in percent; a per-browser convenience, so storage failures fall back to the default. */
export function loadSplit(): number {
  try {
    const stored = Number(localStorage.getItem(SPLIT_STORAGE_KEY));
    return stored ? clampSplit(stored) : DEFAULT_SPLIT;
  } catch {
    return DEFAULT_SPLIT;
  }
}

export function saveSplit(percent: number): void {
  try {
    localStorage.setItem(SPLIT_STORAGE_KEY, String(clampSplit(percent)));
  } catch {
    /* private mode / blocked storage: not remembered */
  }
}
