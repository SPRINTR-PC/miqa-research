// #283 size guard: grid estimate from /metadata, the 2.5 GiB budget (replacement, annotate reserve,
// labelmaps), GPU texture limits and the reduced-3D decimation. Pure, no CS3D.
import { describe, expect, it } from "vitest";

import type { LoadedSeries } from "./series.ts";
import {
  BUDGET_BYTES,
  GIB,
  SizeGuard,
  checkBudget,
  checkImageTexture,
  fitVolume,
  isTooLargeError,
  seriesGrid,
  volumeEntries,
  type BudgetEntry,
  type GpuLimits,
} from "./size-guard.ts";

const MIB = 1024 ** 2;
const DESKTOP: GpuLimits = { max3dTextureSize: 2048, maxTextureSize: 16384 };

function series(n: number, tags: Record<string, unknown[]> = {}): LoadedSeries {
  const instance = {
    "00080060": { vr: "CS", Value: ["CT"] },
    "00280010": { vr: "US", Value: [512] },
    "00280011": { vr: "US", Value: [512] },
    "00280002": { vr: "US", Value: [1] },
    "00280100": { vr: "US", Value: [16] },
    "00280103": { vr: "US", Value: [1] },
    "00281052": { vr: "DS", Value: [-1024] },
    "00281053": { vr: "DS", Value: [1] },
    ...Object.fromEntries(Object.entries(tags).map(([tag, Value]) => [tag, { vr: "XX", Value }])),
  };
  const images = Array.from({ length: n }, (_, i) => ({ imageId: `wadors:x/frames/${i + 1}`, instance }));
  return { ref: { wadoRoot: "/api", studyUid: "1", seriesUid: "2" }, images };
}

describe("seriesGrid", () => {
  it("is rows × columns × slices at 2 B for integer-rescaled 16-bit CT (500 MiB for 512² × 1000)", () => {
    const grid = seriesGrid(series(1000))!;
    expect(grid).toEqual({ rows: 512, columns: 512, slices: 1000, bytesPerVoxel: 2 });
    expect(grid.rows * grid.columns * grid.slices * grid.bytesPerVoxel).toBe(500 * MIB);
  });

  it("counts float-rescaled 16-bit (PET SUV) at 4 B and RGB 8-bit at 3 B", () => {
    expect(seriesGrid(series(2, { "00080060": ["PT"], "00281053": [0.37] }))!.bytesPerVoxel).toBe(4);
    expect(seriesGrid(series(2, { "00080060": ["PT"], "00281053": [1], "00281052": [0] }))!.bytesPerVoxel).toBe(4);
    expect(seriesGrid(series(2, { "00280100": [8], "00280002": [3] }))!.bytesPerVoxel).toBe(3);
  });
});

describe("checkBudget", () => {
  const ct1000: BudgetEntry = { id: "volume:a", series: "a", kind: "volume", bytes: 1000 * MIB };

  it("fits while all open volumes plus the addition stay within 2.5 GiB", () => {
    const open = [ct1000];
    expect(checkBudget(open, { add: [{ id: "volume:b", series: "b", kind: "volume", bytes: 1500 * MIB }] })).toMatchObject({
      ok: true,
      used: 2500 * MIB,
    });
    const tooMuch = checkBudget(open, { add: [{ id: "volume:b", series: "b", kind: "volume", bytes: 1600 * MIB }] });
    expect(tooMuch).toMatchObject({ ok: false, needed: 1600 * MIB, free: 1560 * MIB });
    expect(BUDGET_BYTES).toBe(2.5 * GIB);
  });

  it("removes the series being replaced before counting", () => {
    const open = [ct1000, { id: "volume:b", series: "b", kind: "volume", bytes: 1000 * MIB } as BudgetEntry];
    const add = [{ id: "volume:c", series: "c", kind: "volume", bytes: 1500 * MIB } as BudgetEntry];

    expect(checkBudget(open, { add }).ok).toBe(false);
    expect(checkBudget(open, { add, replaceSeries: ["b"] })).toMatchObject({ ok: true, used: 2500 * MIB });
  });

  it("counts one labelmap reserve per base series, which the first labelmap uses up", () => {
    const reserve: BudgetEntry = { id: "reserve:a", series: "a", kind: "labelmap-reserve", bytes: 500 * MIB };
    const labelmap = (id: string): BudgetEntry => ({ id, series: "a", kind: "labelmap", bytes: 500 * MIB });

    expect(checkBudget([ct1000, reserve], {})).toMatchObject({ used: 1500 * MIB });
    expect(checkBudget([ct1000, reserve], { add: [labelmap("seg1")] })).toMatchObject({ ok: true, used: 1500 * MIB });
    expect(checkBudget([ct1000, reserve, labelmap("seg1")], { add: [labelmap("seg2")] })).toMatchObject({
      ok: true,
      used: 2000 * MIB,
    });
  });
});

describe("fitVolume", () => {
  it("fits a 1000-slice CT, reserving a labelmap for an annotate role", () => {
    const fit = fitVolume(seriesGrid(series(1000))!, "s", DESKTOP, [], { annotate: true });
    expect(fit.ok).toBe(true);
    expect(fit.ok && fit.entries.map((e) => [e.kind, e.bytes])).toEqual([
      ["volume", 500 * MIB],
      ["labelmap-reserve", 250 * MIB],
    ]);
    const viewOnly = fitVolume(seriesGrid(series(1000))!, "s", DESKTOP, [], { annotate: false });
    expect(viewOnly.ok && viewOnly.entries.map((e) => e.kind)).toEqual(["volume"]);
  });

  it("refuses more slices than MAX_3D_TEXTURE_SIZE and offers a k-decimated reduced 3D", () => {
    const fit = fitVolume(seriesGrid(series(3000))!, "s", DESKTOP, [], { annotate: true });
    expect(fit).toMatchObject({ ok: false, reason: "texture", reduced: [1, 1, 2] });
    expect(!fit.ok && fit.message).toContain("3000 slices");
    expect(!fit.ok && fit.message).toContain("2048");
  });

  it("refuses a volume over budget (with the annotate reserve) and decimates k until it fits, without a reserve", () => {
    // 512² × 2000 × 2 B = 1000 MiB, + 500 MiB reserve; 1200 MiB already open → over 2.5 GiB.
    const open: BudgetEntry[] = [{ id: "volume:o", series: "o", kind: "volume", bytes: 1200 * MIB }];
    const grid = seriesGrid(series(2000))!;
    expect(fitVolume(grid, "s", DESKTOP, open, { annotate: false }).ok).toBe(true);

    const fit = fitVolume(grid, "s", DESKTOP, open, { annotate: true });
    expect(fit).toMatchObject({ ok: false, reason: "budget", reduced: [1, 1, 1] });

    const bigger = fitVolume(grid, "s", DESKTOP, [{ ...open[0], bytes: 2000 * MIB }], { annotate: true });
    // 560 MiB free: k = 2 → 500 MiB.
    expect(bigger).toMatchObject({ ok: false, reason: "budget", reduced: [1, 1, 2] });
  });

  it("decimates in-plane only when rows or columns exceed the 3D texture limit", () => {
    const fit = fitVolume(seriesGrid(series(16, { "00280010": [64], "00280011": [64] }))!, "s", { ...DESKTOP, max3dTextureSize: 32 }, [], {
      annotate: true,
    });
    expect(fit).toMatchObject({ ok: false, reason: "texture", reduced: [2, 2, 1] });
  });

  it("replaces the same series' earlier entries before counting", () => {
    const grid = seriesGrid(series(2000))!;
    const open: BudgetEntry[] = [{ id: "volume:s", series: "s", kind: "volume", bytes: 2000 * MIB }];
    expect(fitVolume(grid, "s", DESKTOP, open, { annotate: true }).ok).toBe(true);
  });

  it("keeps the series' extra labelmaps counted when its volume is re-checked", () => {
    const grid = seriesGrid(series(2000))!; // 1000 MiB volume, 500 MiB reserve
    const labelmap = (id: string): BudgetEntry => ({ id, series: "s", kind: "labelmap", bytes: 500 * MIB });
    const open = [...volumeEntries("s", grid, true), labelmap("seg1"), labelmap("seg2"), labelmap("seg3")];
    // 1000 + 3 × 500 = 2500 MiB fits; a fourth labelmap's worth does not.
    expect(fitVolume(grid, "s", DESKTOP, open, { annotate: true }).ok).toBe(true);
    expect(fitVolume(grid, "s", DESKTOP, [...open, labelmap("seg4")], { annotate: true }).ok).toBe(false);
  });
});

describe("checkImageTexture", () => {
  it("refuses a 2D image wider or taller than MAX_TEXTURE_SIZE", () => {
    expect(checkImageTexture(series(1), DESKTOP)).toEqual({ ok: true });
    const big = checkImageTexture(series(1, { "00280011": [20000] }), DESKTOP);
    expect(big).toMatchObject({ ok: false });
    expect(!big.ok && big.message).toContain("16384");
  });
});

describe("SizeGuard", () => {
  const vol = (series: string, mib: number): BudgetEntry => ({ id: `volume:${series}`, series, kind: "volume", bytes: mib * MIB });

  it("reserve commits only when the check passes; release frees", () => {
    const guard = new SizeGuard();
    expect(guard.reserve([vol("a", 2000)]).ok).toBe(true);
    expect(guard.reserve([vol("b", 1000)]).ok).toBe(false);
    expect(guard.used()).toBe(2000 * MIB);

    guard.releaseSeries("a");
    expect(guard.reserve([vol("b", 1000)]).ok).toBe(true);
    expect(guard.used()).toBe(1000 * MIB);
  });

  it("reserveLabelmap uses the base series' reserve first, then refuses one over budget", () => {
    const guard = new SizeGuard();
    guard.reserve([vol("a", 1500), { id: "reserve:a", series: "a", kind: "labelmap-reserve", bytes: 500 * MIB }]);

    expect(guard.reserveLabelmap("a", "seg1", 500 * MIB).ok).toBe(true);
    expect(guard.used()).toBe(2000 * MIB);
    const second = guard.reserveLabelmap("a", "seg2", 600 * MIB);
    expect(second.ok).toBe(false);
    expect(!second.ok && second.message).toMatch(/save and close/i);

    guard.release("seg1");
    expect(guard.used()).toBe(2000 * MIB); // the reserve is back
  });
});

describe("isTooLargeError", () => {
  it("recognises CS3D's cache-full and not-cacheable errors", () => {
    expect(isTooLargeError(new Error("CACHE_SIZE_EXCEEDED"))).toBe(true);
    expect(isTooLargeError(new Error("Cannot created derived volume: Volume with id x is not cacheable."))).toBe(true);
    expect(isTooLargeError(new Error("network"))).toBe(false);
  });
});
