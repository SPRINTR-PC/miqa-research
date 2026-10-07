// Measurement units: CS3D's raw suffixes (`mm Proj`, `mm ERMF`, …) are shown unchanged (spec),
// each with a plain-language tooltip. The calibration legend panel is #281's.

const BY_SUFFIX: Record<string, string> = {
  "": "Millimetres from the image's pixel spacing.",
  Proj: "Projection X-ray, measured in the detector plane (ImagerPixelSpacing). Magnification is not corrected: sizes at the patient are overestimated.",
  ERMF: "Corrected with the Estimated Radiographic Magnification Factor. An estimate, typically within ±10%.",
  Unknown: "Pixel spacing of unverified origin (e.g. a secondary capture). Treat measurements with care.",
  User: "Calibrated by a user against a known length.",
  Error: "The image's pixel spacing tags disagree. Measurements may be wrong.",
  "US Region": "Ultrasound region calibration (SequenceOfUltrasoundRegions). Valid only inside the region.",
};

const PIXELS = "No pixel spacing in the image: measurements are in pixels.";

/** Tooltip for a CS3D length or area unit (`mm`, `mm² Proj`, `px`, `cm US Region`); "" if unknown. */
export function unitTooltip(unit: string): string {
  const [base, ...rest] = unit.trim().split(" ");
  const length = base.replace(/[²³]$/, "");
  if (length === "px") return PIXELS;
  if (!["mm", "cm"].includes(length)) return "";
  return BY_SUFFIX[rest.join(" ")] ?? "";
}
