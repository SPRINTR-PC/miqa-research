// Douglas–Peucker contour simplification (spec "Drawing on WSI", #289): freehand contours on a slide
// are simplified before the SR is built, at a tolerance of 1 screen pixel at the zoom they were drawn at
// (in world mm). Pure, 3D (CS3D world points).

export type Point3 = [number, number, number];

/** Distance from `p` to the segment `a`–`b`. */
function distanceToSegment(p: Point3, a: Point3, b: Point3): number {
  const ab = [b[0] - a[0], b[1] - a[1], b[2] - a[2]];
  const ap = [p[0] - a[0], p[1] - a[1], p[2] - a[2]];
  const len2 = ab[0] ** 2 + ab[1] ** 2 + ab[2] ** 2;
  const t = len2 ? Math.max(0, Math.min(1, (ap[0] * ab[0] + ap[1] * ab[1] + ap[2] * ab[2]) / len2)) : 0;
  return Math.hypot(ap[0] - t * ab[0], ap[1] - t * ab[1], ap[2] - t * ab[2]);
}

/** Open polyline: keeps both ends and every point farther than `tolerance` from the simplified line. */
function simplifyOpen(points: Point3[], tolerance: number): Point3[] {
  const keep = new Array<boolean>(points.length).fill(false);
  keep[0] = keep[points.length - 1] = true;
  const stack: [number, number][] = [[0, points.length - 1]];
  while (stack.length) {
    const [first, last] = stack.pop()!;
    let farthest = -1;
    let max = tolerance;
    for (let i = first + 1; i < last; i++) {
      const d = distanceToSegment(points[i], points[first], points[last]);
      if (d > max) [max, farthest] = [d, i];
    }
    if (farthest < 0) continue;
    keep[farthest] = true;
    stack.push([first, farthest], [farthest, last]);
  }
  return points.filter((_, i) => keep[i]);
}

/**
 * Simplify a contour. A closed contour (first point not repeated at the end) is split at the point
 * farthest from its first point and each half simplified; it keeps at least three points.
 */
export function simplifyContour(points: Point3[], tolerance: number, closed: boolean): Point3[] {
  if (points.length <= (closed ? 3 : 2)) return points.map((p) => [...p] as Point3);
  if (!closed) return simplifyOpen(points, tolerance);
  const fromFirst = (p: Point3) => Math.hypot(p[0] - points[0][0], p[1] - points[0][1], p[2] - points[0][2]);
  let split = 1;
  for (let i = 2; i < points.length; i++) if (fromFirst(points[i]) > fromFirst(points[split])) split = i;
  const first = simplifyOpen(points.slice(0, split + 1), tolerance);
  const second = simplifyOpen([...points.slice(split), points[0]], tolerance);
  const result = [...first, ...second.slice(1, -1)];
  return result.length >= 3 ? result : points.map((p) => [...p] as Point3);
}
