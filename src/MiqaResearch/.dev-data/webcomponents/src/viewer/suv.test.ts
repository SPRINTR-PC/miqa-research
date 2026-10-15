// SUV inputs (#284): which PET series can be SUV-scaled, and why not. Seam: suvInputs / suvStatusFor.
import { describe, expect, it } from "vitest";

import type { DicomJsonInstance, LoadedSeries } from "./series.ts";
import { suvInputs, suvStatusFor } from "./suv.ts";
import { petInstance } from "./test-fixtures.ts";

const series = (instances: DicomJsonInstance[]): LoadedSeries => ({
  ref: { wadoRoot: "/w", studyUid: "1", seriesUid: "2" },
  images: instances.map((instance, i) => ({ imageId: `wadors:/w/${i}`, instance })),
});

describe("suvInputs", () => {
  it("maps a complete PET instance to calculate-suv's input", () => {
    const result = suvInputs([petInstance()]);

    expect(result).toEqual({
      ok: true,
      inputs: [
        {
          CorrectedImage: ["ATTN", "DECY"],
          Units: "BQML",
          RadionuclideHalfLife: 6586.2,
          RadionuclideTotalDose: 370000000,
          RadiopharmaceuticalStartTime: "110000",
          DecayCorrection: "START",
          PatientWeight: 75,
          SeriesDate: "20260101",
          SeriesTime: "120000",
          AcquisitionDate: "20260101",
          AcquisitionTime: "120000",
        },
      ],
    });
  });

  it("leaves out a PatientSex other than M or F (only SUVlbm needs it; calculate-suv throws on O)", () => {
    const result = suvInputs([petInstance({ "00100040": { vr: "CS", Value: ["O"] } })]);

    expect(result.ok && "PatientSex" in result.inputs[0]).toBe(false);
    expect(suvInputs([petInstance({ "00100040": { vr: "CS", Value: ["F"] } })])).toMatchObject({ ok: true, inputs: [{ PatientSex: "F" }] });
  });

  it("names the missing tags", () => {
    const result = suvInputs([petInstance({ "00101030": undefined, "00540016": undefined })]);

    expect(result).toEqual({ ok: false, reason: "missing PatientWeight, RadiopharmaceuticalInformationSequence" });
  });

  it("refuses units other than Bq/ml", () => {
    const result = suvInputs([petInstance({ "00541001": { vr: "LO", Value: ["CNTS"] } })]);

    expect(result).toEqual({ ok: false, reason: "Units are CNTS, not BQML" });
  });
});

describe("suvStatusFor", () => {
  it("is undefined for other modalities", () => {
    expect(suvStatusFor(series([{ "00080060": { vr: "CS", Value: ["CT"] } }]))).toBeUndefined();
  });

  it("reports a PET without the inputs as not applied", () => {
    expect(suvStatusFor(series([petInstance({ "00101030": undefined })]))).toEqual({
      applied: false,
      reason: "missing PatientWeight",
    });
  });

  it("reports a complete PET as applied", () => {
    expect(suvStatusFor(series([petInstance()]))).toEqual({ applied: true });
  });
});
