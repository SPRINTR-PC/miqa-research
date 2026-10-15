import { describe, expect, it } from "vitest";

import { simplifyContour, type Point3 } from "./simplify.ts";

describe("simplifyContour (Douglas–Peucker, WSI freehand #289)", () => {
  it("drops points closer to the line than the tolerance and keeps the corners", () => {
    // An L with a 0.4 wobble on its first leg; tolerance 1.
    const line: Point3[] = [
      [0, 0, 0], [2, 0.4, 0], [4, 0, 0], [6, -0.4, 0], [10, 0, 0], [10, 5, 0], [10, 10, 0],
    ];
    expect(simplifyContour(line, 1, false)).toEqual([[0, 0, 0], [10, 0, 0], [10, 10, 0]]);
  });

  it("keeps a point farther than the tolerance", () => {
    const line: Point3[] = [[0, 0, 0], [5, 3, 0], [10, 0, 0]];
    expect(simplifyContour(line, 1, false)).toEqual(line);
  });

  it("measures distance in 3D", () => {
    const line: Point3[] = [[0, 0, 0], [5, 0, 2], [10, 0, 0]];
    expect(simplifyContour(line, 1, false)).toHaveLength(3);
    expect(simplifyContour(line, 3, false)).toHaveLength(2);
  });

  it("simplifies a closed contour without repeating its first point", () => {
    // A square with an extra point near the middle of every side.
    const square: Point3[] = [
      [0, 0, 0], [5, 0.1, 0], [10, 0, 0], [9.9, 5, 0], [10, 10, 0], [5, 9.9, 0], [0, 10, 0], [0.1, 5, 0],
    ];
    expect(simplifyContour(square, 0.5, true)).toEqual([[0, 0, 0], [10, 0, 0], [10, 10, 0], [0, 10, 0]]);
  });

  it("leaves contours too short to simplify alone", () => {
    expect(simplifyContour([[0, 0, 0], [1, 1, 0]], 5, false)).toEqual([[0, 0, 0], [1, 1, 0]]);
    expect(simplifyContour([[0, 0, 0], [1, 0, 0], [0, 1, 0]], 5, true)).toHaveLength(3);
  });
});
