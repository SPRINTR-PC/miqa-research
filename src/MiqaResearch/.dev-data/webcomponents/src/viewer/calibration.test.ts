// #281 spacing calibration: the per-viewport legend, the SC spacing shim and the burned-in warning.
// Seam: pure functions over CS3D's raw unit string and the served DICOM JSON instance.
import { describe, expect, it } from "vitest";

import { burnedInWarning, calibrationLegend, secondaryCaptureSpacing } from "./calibration.ts";
import type { DicomJsonInstance } from "./series.ts";

const SC = "1.2.840.10008.5.1.4.1.1.7";
const CT = "1.2.840.10008.5.1.4.1.1.2";
const US = "1.2.840.10008.5.1.4.1.1.6.1";
const CR = "1.2.840.10008.5.1.4.1.1.1";

function instance(sopClass: string, extra: DicomJsonInstance = {}): DicomJsonInstance {
  return { "00080016": { vr: "UI", Value: [sopClass] }, ...extra };
}

const spacing = (row: number, col: number) => ({ "00280030": { vr: "DS", Value: [row, col] } });
const burnedIn = (value: string) => ({ "00280301": { vr: "CS", Value: [value] } });

describe("calibrationLegend", () => {
  it.each([
    ["mm Calibrated", "Calibrated", "ok"],
    ["mm ERMF", "ERMF", "ok"],
    ["mm Proj", "Detector plane (Proj)", "warn"],
    ["cm US Region", "US regions", "ok"],
    ["px", "No spacing (px)", "warn"],
    ["mm User", "User-calibrated", "warn"],
  ])("names %s as %s", (unit, badge, level) => {
    expect(calibrationLegend(unit, instance(CR))).toMatchObject({ badge, level });
  });

  it("warns that projection spacing is at the detector plane", () => {
    expect(calibrationLegend("mm Proj", instance(CR))?.text).toMatch(/detector plane.*overestimated/i);
  });

  it("labels Unknown spacing on a secondary capture as unverified SC", () => {
    const legend = calibrationLegend("mm Unknown", instance(SC, spacing(0.5, 0.5)));

    expect(legend?.badge).toBe("Unverified (SC)");
    expect(legend?.text).toBe("Spacing from secondary capture — unverified");
  });

  it("labels Unknown spacing elsewhere as unverified", () => {
    expect(calibrationLegend("mm Unknown", instance(CR))?.badge).toBe("Unverified");
  });

  it("is hidden for plain tomographic mm", () => {
    expect(calibrationLegend("mm", instance(CT))).toBeUndefined();
    expect(calibrationLegend("", instance(CT))).toBeUndefined();
  });
});

describe("secondaryCaptureSpacing: the SC shim", () => {
  it("gives a secondary capture's PixelSpacing as row/column spacing", () => {
    expect(secondaryCaptureSpacing(instance(SC, spacing(0.4, 0.6)))).toEqual({
      rowPixelSpacing: 0.4,
      columnPixelSpacing: 0.6,
    });
  });

  it("covers every SC SOP class (multi-frame too)", () => {
    for (const uid of [SC, `${SC}.1`, `${SC}.2`, `${SC}.3`, `${SC}.4`]) {
      expect(secondaryCaptureSpacing(instance(uid, spacing(1, 1)))).toBeDefined();
    }
  });

  it("leaves SC without spacing and other SOP classes alone", () => {
    expect(secondaryCaptureSpacing(instance(SC))).toBeUndefined();
    expect(secondaryCaptureSpacing(instance(CT, spacing(1, 1)))).toBeUndefined();
  });
});

describe("burnedInWarning", () => {
  it("warns when BurnedInAnnotation is YES", () => {
    expect(burnedInWarning(instance(CT, burnedIn("YES")))).toBe(true);
  });

  it("warns when the tag is missing on SC or US", () => {
    expect(burnedInWarning(instance(SC))).toBe(true);
    expect(burnedInWarning(instance(US))).toBe(true);
  });

  it("is quiet for NO, and for a missing tag on other SOP classes", () => {
    expect(burnedInWarning(instance(SC, burnedIn("NO")))).toBe(false);
    expect(burnedInWarning(instance(CT))).toBe(false);
    expect(burnedInWarning(undefined)).toBe(false);
  });
});
