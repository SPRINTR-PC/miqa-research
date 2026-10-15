// Fusion (spec #271 "Three views and fusion", "Chrome, mouse and tools"; #284). Pure, no CS3D.
//   - Drop a series from the series list onto the big view: top half fuses (into every view),
//     bottom half replaces. Fusion: volumes only, same Frame of Reference, no resampling.
//   - Every layer has a window (W/L, SUV for PET), a curated vtk.js colormap and, for overlays,
//     an opacity transfer curve in data units (CS3D `opacityMapping`) times an overall multiplier.
//   - Over-budget overlays are refused by the size guard (#283); replacing still works.
import type { VoiRange } from "./adapter/adapter.ts";
import { isReconstructable } from "./reconstructable.ts";
import type { LoadedSeries } from "./series.ts";
import { refusalMessage, seriesGrid, textureOverflow, volumeEntries, type BudgetEntry, type GpuLimits, type SizeGuard } from "./size-guard.ts";
import type { SuvStatus } from "./suv.ts";

/** One breakpoint of an opacity transfer curve: `value` in data units (HU, SUV), opacity 0–1. */
export interface OpacityPoint {
  value: number;
  opacity: number;
}

/** How a layer is drawn (its window is separate: the view's VOI of that volume). */
export interface LayerDisplay {
  /** vtk.js colormap preset name (one of COLORMAPS). */
  colormap: string;
  /** Overall opacity multiplier, 0–1. */
  opacity: number;
  /** Opacity transfer curve; empty = flat `opacity`. */
  curve: OpacityPoint[];
}

/**
 * Curated vtk.js presets. CS3D's own colormap registry starts empty; 5.10.11 resolves names it
 * doesn't know against vtk.js's presets (`utilities.colormap.resolveColormap`), so these names work as is.
 */
export const COLORMAPS: readonly string[] = [
  "Grayscale",
  "X Ray",
  "hsv",
  "jet",
  "Black-Body Radiation",
  "Inferno (matplotlib)",
  "Viridis (matplotlib)",
  "Plasma (matplotlib)",
  "Cool to Warm",
  "Rainbow Desaturated",
  "Reds",
  "Greens",
];

/** PET overlay default: transparent up to SUV 2, opaque from SUV 4. */
export const PET_OPACITY_CURVE: readonly OpacityPoint[] = [
  { value: 0, opacity: 0 },
  { value: 2, opacity: 0 },
  { value: 4, opacity: 1 },
];

const PET_SUV_WINDOW: VoiRange = { lower: 0, upper: 5 };

const TAG = { Modality: "00080060", SeriesDescription: "0008103E", FrameOfReferenceUID: "00200052" } as const;

const firstText = (series: LoadedSeries, tag: string) => String(series.images[0]?.instance[tag]?.Value?.[0] ?? "");

export function modalityOf(series: LoadedSeries): string {
  return firstText(series, TAG.Modality);
}

export function frameOfReference(series: LoadedSeries): string {
  return firstText(series, TAG.FrameOfReferenceUID);
}

/** "PT PET AC": modality and description (or the UID). */
export function seriesLabel(series: LoadedSeries): string {
  return [modalityOf(series), firstText(series, TAG.SeriesDescription) || series.ref.seriesUid].filter(Boolean).join(" ");
}

/** Default display of a layer; PET overlays in SUV get the SUV 0–5 window and the default curve. */
export function layerDisplay(modality: string, { base, suv }: { base: boolean; suv?: SuvStatus }): LayerDisplay & { voi?: VoiRange } {
  if (base) return { colormap: "Grayscale", opacity: 1, curve: [] };
  if (modality === "PT" && suv?.applied) return { colormap: "hsv", opacity: 1, curve: PET_OPACITY_CURVE.map((p) => ({ ...p })), voi: { ...PET_SUV_WINDOW } };
  if (modality === "PT") return { colormap: "hsv", opacity: 0.5, curve: [] };
  return { colormap: "Black-Body Radiation", opacity: 0.5, curve: [] };
}

export interface FuseRequest {
  base: LoadedSeries;
  overlay: LoadedSeries;
  /** Series UIDs in view now (base first). */
  shown: string[];
  /** Reduced 3D (#283) is shown: view only, no fusion. */
  reduced: boolean;
  /** The size guard's reason the base can't be a full-resolution volume; undefined when it fits. */
  baseTooLarge: string | undefined;
}

/** Why `overlay` can't be fused onto the base, or undefined if it can (the budget is checked separately). */
export function fuseBlocker({ base, overlay, shown, reduced, baseTooLarge }: FuseRequest): string | undefined {
  const label = seriesLabel(overlay);
  if (shown.includes(overlay.ref.seriesUid)) return `${label} is already shown.`;
  if (reduced) return "Fusion is off in reduced 3D (view only). Drop on the bottom half to replace instead.";
  if (baseTooLarge) return `Fusion is off: ${baseTooLarge}`;
  const baseMpr = isReconstructable(base);
  if (!baseMpr.ok) return `Can't fuse onto ${seriesLabel(base)}: fusion needs volumes (${baseMpr.reason}).`;
  const mpr = isReconstructable(overlay);
  if (!mpr.ok) return `Can't fuse ${label}: fusion needs volumes (${mpr.reason}).`;
  const frame = frameOfReference(overlay);
  if (!frame || !frameOfReference(base)) return `Can't fuse ${label} onto ${seriesLabel(base)}: no Frame of Reference to register them by.`;
  if (frame !== frameOfReference(base)) {
    return `Can't fuse ${label} onto ${seriesLabel(base)}: different Frame of Reference, so they aren't registered to each other.`;
  }
  return undefined;
}

/** Why `next` can't replace what's shown, or undefined. */
export function replaceBlocker(next: LoadedSeries, shown: string[]): string | undefined {
  return shown.length === 1 && shown[0] === next.ref.seriesUid ? `${seriesLabel(next)} is already shown.` : undefined;
}

/**
 * Size guard for a fusion overlay (#283): its volume entry (no labelmap reserve), checked against the
 * budget (not reserved), and refused beyond the GPU's 3D texture limit (no reduced fusions).
 */
export function overlayBudget(
  overlay: LoadedSeries,
  gpu: GpuLimits,
  budget: SizeGuard,
  extra: BudgetEntry[] = [],
): { ok: true; entries: BudgetEntry[] } | { ok: false; message: string } {
  const grid = seriesGrid(overlay);
  if (!grid) return { ok: false, message: "Can't fuse: the series has no images." };
  const overflow = textureOverflow(grid, gpu);
  if (overflow) return { ok: false, message: `Can't fuse: ${overflow}. Drop on the bottom half to replace instead.` };
  const entries = volumeEntries(overlay.ref.seriesUid, grid, false);
  const check = budget.check([...extra, ...entries]);
  return check.ok ? { ok: true, entries } : { ok: false, message: refusalMessage("fusion", check) };
}

/**
 * Right-drag W/L of a fused overlay (#284; CS3D's WindowLevelTool only windows a viewport's first
 * volume): drag right widens, drag down lowers the level, each pixel 1/200 of the current width.
 */
export function dragWindow({ lower, upper }: VoiRange, dx: number, dy: number): VoiRange {
  const width = Math.max(upper - lower, 1e-6);
  const step = width / 200;
  const nextWidth = Math.max(width + dx * step, width / 100);
  const center = (upper + lower) / 2 - dy * step;
  return { lower: center - nextWidth / 2, upper: center + nextWidth / 2 };
}

const clamp01 =(n: number) => Math.min(1, Math.max(0, n));

const sorted = (curve: OpacityPoint[]) => [...curve].sort((a, b) => a.value - b.value);

/** The curve with breakpoint `index` moved to `point` (opacity clamped), sorted by value. */
export function setCurvePoint(curve: readonly OpacityPoint[], index: number, point: OpacityPoint): OpacityPoint[] {
  return sorted(curve.map((p, i) => (i === index ? { value: point.value, opacity: clamp01(point.opacity) } : { ...p })));
}

export function addCurvePoint(curve: readonly OpacityPoint[], point: OpacityPoint): OpacityPoint[] {
  return sorted([...curve.map((p) => ({ ...p })), { value: point.value, opacity: clamp01(point.opacity) }]);
}

export function removeCurvePoint(curve: readonly OpacityPoint[], index: number): OpacityPoint[] {
  return curve.filter((_, i) => i !== index).map((p) => ({ ...p }));
}
