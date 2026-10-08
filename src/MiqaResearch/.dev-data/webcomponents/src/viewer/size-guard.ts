// Size guard (spec #271 "Oversized series and fusions", #283). Pure, no CS3D.
//
// CS3D's image cache (3 GiB) never evicts the images of a cached volume, so everything open at once
// must fit. The guard checks before loading, from /metadata (rows × columns × slices × bytes per
// voxel) and the GPU's MAX_3D_TEXTURE_SIZE / MAX_TEXTURE_SIZE:
//   - Budget 2.5 GiB: all open volumes, plus one labelmap reserve per base series for annotate roles.
//   - Runs at open and on every add; entries of the series being replaced are removed before counting;
//     a failed check changes nothing (views already open stay).
//   - Too big for 3D → full-resolution stack + banner; "Open reduced 3D (view only)" → decimated volume.
//   - Refused with a message: over-budget fusion overlay (#284), 2D image > MAX_TEXTURE_SIZE, over-budget
//     new labelmap (#286).
// Fusion (#284) and segmentation (#286) use `SizeGuard` (ctx.budget): check / reserve / release, and
// reserveLabelmap. See README.md "Size guard".
import type { DicomJsonInstance, LoadedSeries } from "./series.ts";

export const MIB = 1024 ** 2;
export const GIB = 1024 ** 3;
/** Of CS3D's 3 GiB cache (kept at its default). */
export const BUDGET_BYTES = 2.5 * GIB;

/** WebGL2 limits read at runtime (the adapter's `gpuLimits()`). */
export interface GpuLimits {
  /** MAX_3D_TEXTURE_SIZE: per axis of a volume texture. */
  max3dTextureSize: number;
  /** MAX_TEXTURE_SIZE: width/height of a 2D image texture. */
  maxTextureSize: number;
}

/** WebGL2's guaranteed minimums, for when no context can be created. */
export const WEBGL2_MINIMUM: GpuLimits = { max3dTextureSize: 256, maxTextureSize: 2048 };

/** Volume grid of a series as CS3D would cache it. */
export interface SeriesGrid {
  rows: number;
  columns: number;
  /** Images (frames) in the series. */
  slices: number;
  /** Cache bytes per voxel: CS3D's data type × samples per pixel. */
  bytesPerVoxel: number;
}

/** CS3D `decimatedVolumeLoader` `ijkDecimation`: [columns, rows, slices]. */
export type Decimation = [number, number, number];

export type BudgetKind = "volume" | "labelmap" | "labelmap-reserve";

/** One thing counted against the budget. `series` is the (base) series it belongs to. */
export interface BudgetEntry {
  id: string;
  series: string;
  kind: BudgetKind;
  bytes: number;
}

export interface BudgetChange {
  add?: BudgetEntry[];
  /** Series being replaced: their entries are removed before counting. */
  replaceSeries?: string[];
}

export type BudgetCheck =
  | { ok: true; used: number; budget: number }
  | { ok: false; used: number; budget: number; needed: number; free: number };

const TAG = {
  Modality: "00080060",
  SamplesPerPixel: "00280002",
  Rows: "00280010",
  Columns: "00280011",
  BitsAllocated: "00280100",
  RescaleIntercept: "00281052",
  RescaleSlope: "00281053",
} as const;

const num = (i: DicomJsonInstance, tag: string, fallback: number) => {
  const v = Number(i[tag]?.Value?.[0]);
  return Number.isFinite(v) ? v : fallback;
};

/** Size with one decimal in MiB below 1 GiB, else GiB. */
export function formatBytes(bytes: number): string {
  return bytes >= GIB ? `${(bytes / GIB).toFixed(1)} GiB` : `${Math.round(bytes / MIB)} MiB`;
}

/**
 * Grid of a series from its first instance. Bytes per voxel follow CS3D's `_determineDataType`:
 * 8 → 1, 16 → 2 (4 when rescaled to float: non-integer slope/intercept, or PET with SUV), 32 → 4, 64 → 8;
 * times samples per pixel (RGB = 3).
 */
export function seriesGrid(series: LoadedSeries): SeriesGrid | undefined {
  const first = series.images[0]?.instance;
  if (!first) return undefined;
  const bits = num(first, TAG.BitsAllocated, 16);
  const samples = num(first, TAG.SamplesPerPixel, 1);
  const float =
    !Number.isInteger(num(first, TAG.RescaleSlope, 1)) ||
    !Number.isInteger(num(first, TAG.RescaleIntercept, 0)) ||
    String(first[TAG.Modality]?.Value?.[0] ?? "") === "PT";
  const perSample = bits <= 8 ? 1 : bits === 16 ? (float ? 4 : 2) : bits === 24 ? 1 : bits === 32 ? 4 : 8;
  return { rows: num(first, TAG.Rows, 0), columns: num(first, TAG.Columns, 0), slices: series.images.length, bytesPerVoxel: perSample * samples };
}

/** Grid after CS3D's decimation (in-plane floor, slices every k-th). */
export function decimatedGrid(grid: SeriesGrid, [i, j, k]: Decimation): SeriesGrid {
  return {
    ...grid,
    columns: Math.max(1, Math.floor(grid.columns / i)),
    rows: Math.max(1, Math.floor(grid.rows / j)),
    slices: Math.ceil(grid.slices / k),
  };
}

export function gridBytes(grid: SeriesGrid): number {
  return grid.rows * grid.columns * grid.slices * grid.bytesPerVoxel;
}

/** A labelmap (Uint8) on the grid. */
export function labelmapBytes(grid: SeriesGrid): number {
  return grid.rows * grid.columns * grid.slices;
}

/**
 * Bytes in use: volumes, plus per base series the larger of its labelmap reserve and its labelmaps
 * (the first labelmap uses the reserve up; more cost extra).
 */
export function usedBytes(entries: readonly BudgetEntry[]): number {
  let used = 0;
  const labelmaps = new Map<string, { reserve: number; maps: number }>();
  for (const e of entries) {
    if (e.kind === "volume") {
      used += e.bytes;
      continue;
    }
    const s = labelmaps.get(e.series) ?? { reserve: 0, maps: 0 };
    if (e.kind === "labelmap") s.maps += e.bytes;
    else s.reserve += e.bytes;
    labelmaps.set(e.series, s);
  }
  for (const s of labelmaps.values()) used += Math.max(s.reserve, s.maps);
  return used;
}

/** Entries left after a change: replaced series and re-added ids removed, additions appended. */
function applyChange(open: readonly BudgetEntry[], { add = [], replaceSeries = [] }: BudgetChange): BudgetEntry[] {
  const ids = new Set(add.map((e) => e.id));
  return [...open.filter((e) => !replaceSeries.includes(e.series) && !ids.has(e.id)), ...add];
}

/** The pure budget check: does the open set after `change` stay within `budget`? */
export function checkBudget(open: readonly BudgetEntry[], change: BudgetChange, budget = BUDGET_BYTES): BudgetCheck {
  const after = applyChange(open, change);
  const used = usedBytes(after);
  if (used <= budget) return { ok: true, used, budget };
  const before = usedBytes(applyChange(open, { replaceSeries: change.replaceSeries }));
  return { ok: false, used, budget, needed: used - before, free: Math.max(0, budget - before) };
}

export type VolumeFit =
  | { ok: true; entries: BudgetEntry[]; grid: SeriesGrid }
  | {
      ok: false;
      reason: "texture" | "budget";
      /** Banner text: why the series isn't shown in 3D. */
      message: string;
      /** Decimation for "Open reduced 3D (view only)"; undefined when even that can't fit. */
      reduced: Decimation | undefined;
    };

export interface VolumeFitOptions {
  /** Annotate role: reserve one labelmap on the base series. */
  annotate: boolean;
  budget?: number;
}

const volumeId = (series: string, decimation?: Decimation) =>
  decimation ? `volume:${series}:${decimation.join("-")}` : `volume:${series}`;

/** Budget entries of a series' volume (and the labelmap reserve for annotate roles; none when decimated). */
export function volumeEntries(series: string, grid: SeriesGrid, annotate: boolean, decimation?: Decimation): BudgetEntry[] {
  const g = decimation ? decimatedGrid(grid, decimation) : grid;
  const entries: BudgetEntry[] = [{ id: volumeId(series, decimation), series, kind: "volume", bytes: gridBytes(g) }];
  if (annotate && !decimation) entries.push({ id: `reserve:${series}`, series, kind: "labelmap-reserve", bytes: labelmapBytes(g) });
  return entries;
}

export function textureOverflow(grid: SeriesGrid, limits: GpuLimits): string | undefined {
  const max = limits.max3dTextureSize;
  if (grid.slices > max) return `${grid.slices} slices exceed the GPU's 3D texture limit (${max})`;
  if (grid.rows > max || grid.columns > max) return `${grid.rows} × ${grid.columns} px exceed the GPU's 3D texture limit (${max})`;
  return undefined;
}

/**
 * Whether a series fits as a full-resolution volume (texture limits + budget; the series' own earlier
 * volume entries have the same ids and are replaced, its labelmaps stay counted). If not: why, and the smallest decimation that fits as a view-only volume
 * (in-plane only when rows/columns exceed the 3D texture limit; then every k-th slice; no labelmap reserve).
 */
export function fitVolume(
  grid: SeriesGrid,
  series: string,
  limits: GpuLimits,
  open: readonly BudgetEntry[],
  { annotate, budget = BUDGET_BYTES }: VolumeFitOptions,
): VolumeFit {
  const overflow = textureOverflow(grid, limits);
  let message: string;
  if (overflow) message = `Too large for 3D: ${overflow}.`;
  else {
    const entries = volumeEntries(series, grid, annotate);
    const check = checkBudget(open, { add: entries }, budget);
    if (check.ok) return { ok: true, entries, grid };
    message = `Too large for 3D: needs ${formatBytes(check.needed)}, ${formatBytes(check.free)} of the ${formatBytes(budget)} budget is free.`;
  }

  const max = limits.max3dTextureSize;
  const f = Math.max(1, Math.ceil(grid.rows / max), Math.ceil(grid.columns / max));
  let reduced: Decimation | undefined;
  for (let k = Math.max(1, Math.ceil(grid.slices / max)); Math.ceil(grid.slices / k) >= 2; k++) {
    const d: Decimation = [f, f, k];
    if (checkBudget(open, { add: volumeEntries(series, grid, false, d) }, budget).ok) {
      reduced = d;
      break;
    }
  }
  return { ok: false, reason: overflow ? "texture" : "budget", message, reduced };
}

/** 2D: every image must fit one MAX_TEXTURE_SIZE texture (not WSI, which is tiled). */
export function checkImageTexture(series: LoadedSeries, limits: GpuLimits): { ok: true } | { ok: false; message: string } {
  const max = limits.maxTextureSize;
  for (const { instance } of series.images) {
    const rows = num(instance, TAG.Rows, 0);
    const columns = num(instance, TAG.Columns, 0);
    if (rows > max || columns > max) {
      return { ok: false, message: `Image too large to display: ${columns} × ${rows} px exceeds the GPU's texture limit (${max} px).` };
    }
  }
  return { ok: true };
}

/** CS3D cache errors: an image that doesn't fit, a derived volume (labelmap) that "is not cacheable". */
export function isTooLargeError(e: unknown): boolean {
  const message = e instanceof Error ? e.message : String(e);
  return message.includes("CACHE_SIZE_EXCEEDED") || /not cacheable/i.test(message);
}

export const TOO_LARGE_MESSAGE = "Too large to open with the current views: the image cache is full.";

/** Refusal text for an over-budget check (#284 fusion overlay, #286 new labelmap). */
export function refusalMessage(what: "fusion" | "labelmap", check: Extract<BudgetCheck, { ok: false }>): string {
  const sizes = `needs ${formatBytes(check.needed)}, ${formatBytes(check.free)} of the ${formatBytes(check.budget)} budget is free`;
  return what === "fusion"
    ? `Can't fuse: the overlay ${sizes}. Drop on the bottom half to replace instead.`
    : `Can't add a segmentation: it ${sizes}. Save and close the other Segmentation first.`;
}

export type GuardResult = { ok: true } | { ok: false; check: Extract<BudgetCheck, { ok: false }>; message: string };

/**
 * The viewer's budget ledger (one per element, `ctx.budget`). `check` never changes anything;
 * `reserve` commits only when the check passes. #284 reserves overlay volumes, #286 labelmaps.
 */
export class SizeGuard {
  private entries: BudgetEntry[] = [];
  readonly budget: number;

  constructor(budget = BUDGET_BYTES) {
    this.budget = budget;
  }

  open(): readonly BudgetEntry[] {
    return this.entries;
  }

  used(): number {
    return usedBytes(this.entries);
  }

  check(add: BudgetEntry[], replaceSeries: string[] = []): BudgetCheck {
    return checkBudget(this.entries, { add, replaceSeries }, this.budget);
  }

  reserve(add: BudgetEntry[], replaceSeries: string[] = []): BudgetCheck {
    const check = this.check(add, replaceSeries);
    if (check.ok) this.entries = applyChange(this.entries, { add, replaceSeries });
    return check;
  }

  release(id: string): void {
    this.entries = this.entries.filter((e) => e.id !== id);
  }

  /** Drop every entry of a series (closed or replaced). */
  releaseSeries(series: string): void {
    this.entries = this.entries.filter((e) => e.series !== series);
  }

  /**
   * A new labelmap on base series `series` (#286). The first one uses the series' reserve; one over
   * budget is refused with "save and close the other Segmentation first". Release it with `release(id)`.
   */
  reserveLabelmap(series: string, id: string, bytes: number): GuardResult {
    const check = this.reserve([{ id, series, kind: "labelmap", bytes }]);
    return check.ok ? { ok: true } : { ok: false, check, message: refusalMessage("labelmap", check) };
  }
}
