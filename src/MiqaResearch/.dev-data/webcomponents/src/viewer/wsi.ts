// Whole-slide imaging (WSI, #285): the pure parts, no Cornerstone3D (unit-tested under vitest).
// The WHOLE_SLIDE view itself lives in adapter/cornerstone/wsi.ts.
import type { DicomJsonInstance, LoadedSeries, SeriesImage } from "./series.ts";

/** VL Whole Slide Microscopy Image Storage. */
export const WSI_SOP_CLASS = "1.2.840.10008.5.1.4.1.1.77.1.6";

/** dicom-microscopy-viewer tile cache budget (spec "WSI"); separate from CS3D's cache. */
export const TILE_CACHE_BYTES = 512 * 1024 * 1024;
/** Decoded tiles are RGBA. */
const BYTES_PER_PIXEL = 4;
const DEFAULT_TILE = 512;

/** Left-button tool when a slide opens (no W/L on WSI). */
export const WSI_DEFAULT_TOOL = "Pan";

const TAG = { SOPClassUID: "00080016", Rows: "00280010", Columns: "00280011" } as const;

const first = (instance: DicomJsonInstance, tag: string) => instance[tag]?.Value?.[0];

export function isWholeSlide(series: LoadedSeries): boolean {
  return series.images.some(({ instance }) => first(instance, TAG.SOPClassUID) === WSI_SOP_CLASS);
}

/**
 * dmv `tilesCacheSize`: how many tiles fit 512 MiB, at the pyramid's largest tile
 * (Rows × Columns × 4 B). 512² tiles → 512.
 */
export function tilesCacheSize(instances: DicomJsonInstance[]): number {
  const tilePixels = Math.max(
    0,
    ...instances.map((i) => Number(first(i, TAG.Rows) ?? 0) * Number(first(i, TAG.Columns) ?? 0)),
  );
  const pixels = tilePixels || DEFAULT_TILE * DEFAULT_TILE;
  return Math.max(1, Math.floor(TILE_CACHE_BYTES / (pixels * BYTES_PER_PIXEL)));
}

/**
 * One imageId per instance (pyramid level): WSIViewport takes instances, and dicom-microscopy-viewer
 * builds the tile (`/frames/{n}`) URLs itself.
 */
export function wsiImageIds(series: LoadedSeries): SeriesImage[] {
  const seen = new Set<DicomJsonInstance>();
  return series.images.filter(({ instance }) => !seen.has(instance) && seen.add(instance));
}

/** CS3D annotation `cachedStats` entry (subset). */
export interface MeasurementStats {
  length?: number;
  area?: number;
  perimeter?: number;
  unit?: string;
  areaUnit?: string;
  [stat: string]: unknown;
}

const isNumber = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);

/**
 * Text box lines on WSI: geometric measurements only (length, area, perimeter).
 * Intensity stats (mean, min, max, std dev) are NaN or meaningless on a slide, so they're hidden.
 */
export function geometricTextLines(stats: MeasurementStats | undefined, round: (n: number) => string): string[] {
  if (!stats) return [];
  const lines: string[] = [];
  if (isNumber(stats.area)) lines.push(`Area: ${round(stats.area)} ${stats.areaUnit ?? ""}`.trim());
  if (isNumber(stats.perimeter)) lines.push(`Perimeter: ${round(stats.perimeter)} ${stats.unit ?? ""}`.trim());
  if (isNumber(stats.length)) lines.push(`${round(stats.length)} ${stats.unit ?? ""}`.trim());
  return lines;
}
