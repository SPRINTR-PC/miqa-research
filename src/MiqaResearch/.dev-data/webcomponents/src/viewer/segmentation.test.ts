// #286 segmentation, pure parts: the segment list, the stack threshold fill and polygon rasterising.
import { describe, expect, it } from "vitest";

import { SegmentList, defaultThresholdRange, polygonPixels, thresholdPixels } from "./segmentation.ts";

describe("SegmentList", () => {
  it("starts with Segment 1 active", () => {
    const list = new SegmentList();

    expect(list.active).toBe(1);
    expect(list.segments.map((s) => s.label)).toEqual(["Segment 1"]);
  });

  it("adds the next index, active, with a colour unlike the others", () => {
    const list = new SegmentList();

    const index = list.add();

    expect(index).toBe(2);
    expect(list.active).toBe(2);
    expect(list.segments[1]).toMatchObject({ index: 2, label: "Segment 2" });
    expect(list.segments[1].color).not.toEqual(list.segments[0].color);
  });

  it("renames, recolours and activates a segment; blank names are ignored", () => {
    const list = new SegmentList();
    list.add();

    list.rename(1, "  Liver ");
    list.rename(2, "   ");
    list.setColor(1, [10, 20, 30]);
    list.setActive(1);

    expect(list.segments.map((s) => s.label)).toEqual(["Liver", "Segment 2"]);
    expect(list.segments[0].color).toEqual([10, 20, 30]);
    expect(list.active).toBe(1);
  });

  it("ignores an unknown segment", () => {
    const list = new SegmentList();

    list.setActive(7);
    list.rename(7, "x");

    expect(list.active).toBe(1);
    expect(list.segments).toHaveLength(1);
  });
});

describe("thresholdPixels (stack fill: CS3D's helper is volume-only)", () => {
  // 4 × 3 image, values = column * 10 + row.
  const width = 4;
  const values = Float32Array.from({ length: 12 }, (_, i) => (i % width) * 10 + Math.floor(i / width));

  // Image coordinates as CS3D's worldToImageCoords: pixel (x, y) spans [x, x + 1); its centre decides.
  it("lists the pixels inside the rectangle (clamped to the image) whose value is within [lower, upper]", () => {
    const inside = thresholdPixels(values, width, [[-5, -5], [3, 2]], { lower: 10, upper: 30 });

    // Columns 0–2, rows 0–1: values 10, 20 (row 0) and 11, 21 (row 1); 0 and 1 are below.
    expect(inside).toEqual([1, 2, 5, 6]);
  });

  it("takes the corners in any order and includes both range ends", () => {
    expect(thresholdPixels(values, width, [[4, 3], [0, 0]], { lower: 31, upper: 32 })).toEqual([7, 11]);
  });
});

describe("polygonPixels", () => {
  it("lists the pixels whose centres are inside a closed polygon, clamped to the image", () => {
    // Triangle (0,0) (4,0) (0,4) on a 5 × 5 image: centres (x + 0.5, y + 0.5) with x + y < 3.
    const inside = polygonPixels([[0, 0], [4, 0], [0, 4]], 5, 5);

    expect(inside.sort((a, b) => a - b)).toEqual([0, 1, 2, 5, 6, 10]);
  });

  it("is empty for a polygon off the image", () => {
    expect(polygonPixels([[10, 10], [12, 10], [12, 12]], 5, 5)).toEqual([]);
  });
});

describe("defaultThresholdRange", () => {
  it("is bone-ish HU on CT and SUV 2.5+ on PET", () => {
    expect(defaultThresholdRange("CT")).toEqual({ lower: 300, upper: 3000 });
    expect(defaultThresholdRange("PT")).toEqual({ lower: 2.5, upper: 100 });
  });
});
