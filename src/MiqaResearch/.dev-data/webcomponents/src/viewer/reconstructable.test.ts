import { describe, expect, it } from "vitest";

import { isReconstructable } from "./reconstructable.ts";
import type { DicomJsonInstance, LoadedSeries } from "./series.ts";

const AXIAL = [1, 0, 0, 0, 1, 0];

function slice(z: number, extra: Record<string, unknown[]> = {}): DicomJsonInstance {
  const tags: Record<string, unknown[]> = {
    "00080060": ["CT"],
    "00200032": [0, 0, z],
    "00200037": AXIAL,
    "00280010": [64],
    "00280011": [64],
    "00280002": [1],
    ...extra,
  };
  return Object.fromEntries(Object.entries(tags).map(([tag, Value]) => [tag, { vr: "DS", Value }]));
}

function series(instances: DicomJsonInstance[]): LoadedSeries {
  return {
    ref: { wadoRoot: "/w", studyUid: "1", seriesUid: "2" },
    images: instances.map((instance, i) => ({ imageId: `wadors:/w/f/${i}`, instance })),
  };
}

const evenCt = (n: number, spacing = 2.5) => Array.from({ length: n }, (_, i) => slice(i * spacing));

describe("isReconstructable (OHIF rule)", () => {
  it("accepts an evenly spaced CT", () => {
    expect(isReconstructable(series(evenCt(16)))).toEqual({ ok: true });
  });

  it("refuses a single image", () => {
    expect(isReconstructable(series(evenCt(1))).ok).toBe(false);
  });

  it("refuses modalities other than CT, MR, PT, NM", () => {
    const xa = evenCt(4).map((i) => ({ ...i, "00080060": { vr: "CS", Value: ["CR"] } }));
    expect(isReconstructable(series(xa))).toEqual({ ok: false, reason: "CR series can't be reconstructed" });
  });

  it("refuses slices without a position", () => {
    const s = evenCt(4);
    delete s[2]["00200032"];
    expect(isReconstructable(series(s))).toEqual({ ok: false, reason: "Some images have no position" });
  });

  it("refuses mixed image sizes", () => {
    const s = evenCt(4);
    s[3] = slice(7.5, { "00280010": [32] });
    expect(isReconstructable(series(s))).toEqual({ ok: false, reason: "Images differ in size, samples or orientation" });
  });

  it("refuses mixed orientations", () => {
    const s = evenCt(4);
    s[1] = slice(2.5, { "00200037": [0, 1, 0, 0, 0, -1] });
    expect(isReconstructable(series(s)).ok).toBe(false);
  });

  it("refuses irregular spacing", () => {
    const s = [0, 2.5, 5, 9, 10, 12.5].map((z) => slice(z));
    expect(isReconstructable(series(s))).toEqual({ ok: false, reason: "Slice spacing is irregular" });
  });

  it("accepts tolerance within 20% and a gap of whole missing slices (OHIF: missing frames)", () => {
    expect(isReconstructable(series([0, 2.5, 5.2, 7.5, 10].map((z) => slice(z)))).ok).toBe(true);
    expect(isReconstructable(series([0, 2, 4, 8, 10, 12].map((z) => slice(z)))).ok).toBe(true);
  });

  it("accepts a multi-frame instance only with shared pixel measures", () => {
    const frames = (shared: boolean): LoadedSeries => {
      const instance = slice(0, { "00280008": [10] });
      if (shared) instance["52009229"] = { vr: "SQ", Value: [{ "00289110": { vr: "SQ", Value: [{}] } }] };
      return { ref: series([]).ref, images: Array.from({ length: 10 }, (_, f) => ({ imageId: `f${f}`, instance })) };
    };
    expect(isReconstructable(frames(true)).ok).toBe(true);
    expect(isReconstructable(frames(false)).ok).toBe(false);
  });
});
