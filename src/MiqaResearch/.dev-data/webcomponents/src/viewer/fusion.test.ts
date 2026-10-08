// Fusion rules (#284): what may be fused or replaced, overlay budget, layer defaults, curve edits.
// Seam: the pure functions of fusion.ts.
import { describe, expect, it } from "vitest";

import { dragWindow, fuseBlocker, layerDisplay, overlayBudget, PET_OPACITY_CURVE, replaceBlocker, setCurvePoint, type FuseRequest } from "./fusion.ts";
import type { LoadedSeries } from "./series.ts";
import { GIB, SizeGuard } from "./size-guard.ts";
import { volumeInstances, type VolumeFixture } from "./test-fixtures.ts";

const series = (uid: string, n: number, fixture: VolumeFixture = {}): LoadedSeries => ({
  ref: { wadoRoot: "/w", studyUid: "2.25.1", seriesUid: uid },
  images: volumeInstances(n, fixture).map((instance, i) => ({ imageId: `wadors:/w/${uid}/${i}`, instance })),
});

const ct = series("ct", 8, { description: "Chest CT" });
const pet = series("pet", 8, { modality: "PT", description: "PET AC" });
const request = (overlay: LoadedSeries, more: Partial<FuseRequest> = {}): FuseRequest => ({
  base: ct,
  overlay,
  shown: ["ct"],
  reduced: false,
  baseTooLarge: undefined,
  ...more,
});

describe("fuseBlocker", () => {
  it("lets a volume with the base's Frame of Reference fuse", () => {
    expect(fuseBlocker(request(pet))).toBeUndefined();
  });

  it("refuses a different Frame of Reference, naming both series", () => {
    const other = series("mr", 8, { modality: "MR", frameOfReference: "2.25.99", description: "Brain MR" });

    expect(fuseBlocker(request(other))).toBe(
      "Can't fuse MR Brain MR onto CT Chest CT: different Frame of Reference, so they aren't registered to each other.",
    );
  });

  it("refuses a series without a Frame of Reference", () => {
    const other = series("x", 8, { modality: "PT", frameOfReference: "" });

    expect(fuseBlocker(request(other))).toContain("no Frame of Reference");
  });

  it("refuses a series that isn't a volume", () => {
    const single = series("one", 1, { modality: "PT" });

    expect(fuseBlocker(request(single))).toMatch(/^Can't fuse PT one: fusion needs volumes \(/);
  });

  it("refuses a series already shown", () => {
    expect(fuseBlocker(request(pet, { shown: ["ct", "pet"] }))).toBe("PT PET AC is already shown.");
  });

  it("is off in reduced 3D and when the base is too large for 3D", () => {
    expect(fuseBlocker(request(pet, { reduced: true }))).toContain("reduced 3D");
    expect(fuseBlocker(request(pet, { baseTooLarge: "Too large for 3D: 3000 slices." }))).toBe(
      "Fusion is off: Too large for 3D: 3000 slices.",
    );
  });
});

describe("replaceBlocker", () => {
  it("refuses only the series shown alone", () => {
    expect(replaceBlocker(ct, ["ct"])).toBe("CT Chest CT is already shown.");
    expect(replaceBlocker(ct, ["ct", "pet"])).toBeUndefined();
    expect(replaceBlocker(pet, ["ct"])).toBeUndefined();
  });
});

describe("overlayBudget", () => {
  const gpu = { max3dTextureSize: 2048, maxTextureSize: 16384 };

  it("gives the overlay's volume entry, no labelmap reserve", () => {
    const result = overlayBudget(pet, gpu, new SizeGuard());

    expect(result).toEqual({ ok: true, entries: [{ id: "volume:pet", series: "pet", kind: "volume", bytes: 64 * 64 * 8 * 4 }] });
  });

  it("refuses an overlay over budget with the size guard's fusion message", () => {
    const guard = new SizeGuard(GIB);
    guard.reserve([{ id: "volume:ct", series: "ct", kind: "volume", bytes: GIB }]);

    const result = overlayBudget(pet, gpu, guard);

    expect(result.ok).toBe(false);
    expect(!result.ok && result.message).toContain("Can't fuse: the overlay needs");
  });

  it("refuses an overlay beyond the GPU's 3D texture limit", () => {
    const result = overlayBudget(pet, { ...gpu, max3dTextureSize: 32 }, new SizeGuard());

    expect(!result.ok && result.message).toBe(
      "Can't fuse: 64 × 64 px exceed the GPU's 3D texture limit (32). Drop on the bottom half to replace instead.",
    );
  });
});

describe("layerDisplay", () => {
  it("defaults a PET overlay in SUV to hsv, SUV 0–5 and the 0 % to SUV 2, 100 % from SUV 4 curve", () => {
    expect(layerDisplay("PT", { base: false, suv: { applied: true } })).toEqual({
      colormap: "hsv",
      opacity: 1,
      curve: [
        { value: 0, opacity: 0 },
        { value: 2, opacity: 0 },
        { value: 4, opacity: 1 },
      ],
      voi: { lower: 0, upper: 5 },
    });
    expect(PET_OPACITY_CURVE).toHaveLength(3);
  });

  it("gives a PET overlay in Bq/ml a flat half opacity (an SUV curve would be meaningless)", () => {
    expect(layerDisplay("PT", { base: false, suv: { applied: false, reason: "missing PatientWeight" } })).toEqual({
      colormap: "hsv",
      opacity: 0.5,
      curve: [],
    });
  });

  it("shows the base in grey, opaque", () => {
    expect(layerDisplay("CT", { base: true })).toEqual({ colormap: "Grayscale", opacity: 1, curve: [] });
  });
});

describe("dragWindow", () => {
  it("widens with a drag right and lowers the level with a drag down, 1/200 of the width per pixel", () => {
    expect(dragWindow({ lower: 0, upper: 10 }, 20, 0)).toEqual({ lower: -0.5, upper: 10.5 });
    expect(dragWindow({ lower: 0, upper: 10 }, 0, 20)).toEqual({ lower: -1, upper: 9 });
  });

  it("never collapses the window", () => {
    const voi = dragWindow({ lower: 0, upper: 10 }, -5000, 0);

    expect(voi.upper).toBeGreaterThan(voi.lower);
  });
});

describe("setCurvePoint", () => {
  it("moves a breakpoint, clamps opacity to 0–1 and keeps the curve sorted by value", () => {
    const curve = setCurvePoint(PET_OPACITY_CURVE, 2, { value: 1, opacity: 1.4 });

    expect(curve).toEqual([
      { value: 0, opacity: 0 },
      { value: 1, opacity: 1 },
      { value: 2, opacity: 0 },
    ]);
  });
});
