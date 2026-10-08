// Segmentation (#286), pure parts: the segment list (add, rename, colour, active), the stack threshold
// fill (CS3D's rectangle-threshold helper is volume-only) and polygon rasterising. No CS3D: the
// adapter (adapter/cornerstone/segmentation.ts) feeds them pixel arrays in image coordinates as CS3D's
// `worldToImageCoords` returns them (pixel (x, y) spans [x, x + 1); its centre decides).

export type Rgb = [number, number, number];

export interface Segment {
  /** Labelmap value (1–255). */
  index: number;
  label: string;
  color: Rgb;
}

/** Observable state of the open Segmentation. */
export interface SegmentationState {
  segments: Segment[];
  /** Segment the tools paint. */
  active: number;
  /** Brush size (CS3D `brushSize`). */
  brushSize: number;
  /** Rectangle ROI threshold rectangles drawn and not yet run. */
  thresholdRectangles: number;
}

export const DEFAULT_BRUSH_SIZE = 10;

export interface ValueRange {
  lower: number;
  upper: number;
}

/** Segment colours, cycled; the adapter sets them on the labelmap so the list and the overlay agree. */
const PALETTE: Rgb[] = [
  [221, 84, 84],
  [77, 228, 121],
  [166, 70, 235],
  [189, 180, 116],
  [109, 182, 196],
  [204, 101, 157],
  [123, 211, 94],
  [93, 87, 218],
  [225, 128, 80],
  [73, 232, 172],
];

export const MAX_SEGMENTS = 255;

/** The segments of one Segmentation. Starts with "Segment 1", active. */
export class SegmentList {
  segments: Segment[] = [];
  active = 1;

  constructor() {
    this.add();
  }

  /** Add the next segment and make it active; returns its index (undefined when 255 are used). */
  add(): number | undefined {
    const index = Math.max(0, ...this.segments.map((s) => s.index)) + 1;
    if (index > MAX_SEGMENTS) return undefined;
    this.segments.push({ index, label: `Segment ${index}`, color: [...PALETTE[(index - 1) % PALETTE.length]] as Rgb });
    this.active = index;
    return index;
  }

  get(index: number): Segment | undefined {
    return this.segments.find((s) => s.index === index);
  }

  rename(index: number, label: string): void {
    const segment = this.get(index);
    if (segment && label.trim()) segment.label = label.trim();
  }

  setColor(index: number, color: Rgb): void {
    const segment = this.get(index);
    if (segment) segment.color = [...color] as Rgb;
  }

  setActive(index: number): void {
    if (this.get(index)) this.active = index;
  }
}

/** Start range of the threshold form: HU above soft tissue on CT, SUV ≥ 2.5 on PET. */
export function defaultThresholdRange(modality: string): ValueRange {
  return modality === "PT" ? { lower: 2.5, upper: 100 } : { lower: 300, upper: 3000 };
}

/** `#rrggbb` ↔ RGB, for the colour input. */
export function rgbToHex(color: Rgb): string {
  return `#${color.map((c) => c.toString(16).padStart(2, "0")).join("")}`;
}

export function hexToRgb(hex: string): Rgb {
  const n = parseInt(hex.replace("#", ""), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

/** Pixel columns/rows whose centre lies in [from, to] (any corner order), clamped to `size`. */
function span(a: number, b: number, size: number): [number, number] {
  const lo = Math.max(0, Math.ceil(Math.min(a, b) - 0.5));
  const hi = Math.min(size - 1, Math.floor(Math.max(a, b) - 0.5));
  return [lo, hi];
}

/**
 * Stack threshold: indices (y * width + x) of the pixels inside the rectangle (two opposite corners in
 * image coordinates) whose value (modality units, row-major `values`) is within [lower, upper].
 */
export function thresholdPixels(
  values: ArrayLike<number>,
  width: number,
  rect: [[number, number], [number, number]],
  range: ValueRange,
): number[] {
  const height = Math.floor(values.length / width);
  const [x0, x1] = span(rect[0][0], rect[1][0], width);
  const [y0, y1] = span(rect[0][1], rect[1][1], height);
  const out: number[] = [];
  for (let y = y0; y <= y1; y++) {
    for (let x = x0; x <= x1; x++) {
      const v = values[y * width + x];
      if (v >= range.lower && v <= range.upper) out.push(y * width + x);
    }
  }
  return out;
}

/** Indices (y * width + x) of the pixels whose centre is inside the closed polygon (even–odd rule). */
export function polygonPixels(polygon: [number, number][], width: number, height: number): number[] {
  if (polygon.length < 3) return [];
  const xs = polygon.map((p) => p[0]);
  const ys = polygon.map((p) => p[1]);
  const [x0, x1] = span(Math.min(...xs), Math.max(...xs), width);
  const [y0, y1] = span(Math.min(...ys), Math.max(...ys), height);
  const out: number[] = [];
  for (let y = y0; y <= y1; y++) {
    const cy = y + 0.5;
    for (let x = x0; x <= x1; x++) {
      const cx = x + 0.5;
      let inside = false;
      for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i++) {
        const [xi, yi] = polygon[i];
        const [xj, yj] = polygon[j];
        if (yi > cy !== yj > cy && cx < ((xj - xi) * (cy - yi)) / (yj - yi) + xi) inside = !inside;
      }
      if (inside) out.push(y * width + x);
    }
  }
  return out;
}
