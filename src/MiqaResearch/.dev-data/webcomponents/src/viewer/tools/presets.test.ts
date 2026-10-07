import { describe, expect, it } from "vitest";

import { presetVoi, presets, voiToWindow } from "./presets.ts";

describe("window presets (spec: CT 0–6, PET 7–8)", () => {
  it("offers DICOM default and the six CT presets on a CT, keyed 0–6", () => {
    expect(presets.forModality("CT").map((p) => [p.key, p.label])).toEqual([
      ["0", "DICOM default"],
      ["1", "Soft tissue"],
      ["2", "Lung"],
      ["3", "Bone"],
      ["4", "Brain"],
      ["5", "Liver"],
      ["6", "Mediastinum"],
    ]);
  });

  it("offers SUV 0–5 and 0–10 on a PET, keyed 7 and 8", () => {
    expect(presets.forModality("PT").map((p) => [p.key, p.label])).toEqual([
      ["0", "DICOM default"],
      ["7", "SUV 0–5"],
      ["8", "SUV 0–10"],
    ]);
    expect(presetVoi(presets.forKey("8", "PT")!)).toEqual({ lower: 0, upper: 10 });
  });

  it("offers only DICOM default for other modalities", () => {
    expect(presets.forModality("MR").map((p) => p.id)).toEqual(["dicom"]);
    expect(presets.forKey("2", "MR")).toBeUndefined();
  });

  it("turns a CT window into a linear VOI range (PS3.3 C.11.2.1.2)", () => {
    // Lung W 1500 / L -600 → [L - 0.5 - (W-1)/2, L - 0.5 + (W-1)/2]
    expect(presetVoi(presets.forKey("2", "CT")!)).toEqual({ lower: -1350, upper: 149 });
    expect(voiToWindow({ lower: -1350, upper: 149 })).toEqual({ width: 1500, center: -600 });
  });

  it("has no range for DICOM default (the view resets to the image's own window)", () => {
    expect(presetVoi(presets.forKey("0", "CT")!)).toBeUndefined();
  });
});
