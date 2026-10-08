// Spacing calibration (#281, spec "2D spacing and calibration", #200) and the burned-in badge
// (spec "De-identification Profile"). Pure: CS3D's raw unit string + the served DICOM JSON instance.
// The adapter (adapter/cornerstone/metadata.ts) applies the SC shim; the inspector shows the legend.
import type { DicomJsonInstance } from "./series.ts";
import { unitTooltip } from "./units.ts";

export interface CalibrationLegend {
  /** Short badge text, e.g. "Detector plane (Proj)". */
  badge: string;
  /** "warn": trust the number less than the unit suggests. */
  level: "ok" | "warn";
  /** Plain-language explanation. */
  text: string;
}

const TAG = {
  SOPClassUID: "00080016",
  Modality: "00080060",
  PixelSpacing: "00280030",
  BurnedInAnnotation: "00280301",
} as const;

/** Secondary Capture SOP classes (single-frame, multi-frame bit/byte/word, true colour). */
const SECONDARY_CAPTURE = new Set(["", ".1", ".2", ".3", ".4"].map((s) => `1.2.840.10008.5.1.4.1.1.7${s}`));
/** Ultrasound SOP classes (incl. retired). */
const ULTRASOUND = new Set(["6.1", "3.1", "6", "3"].map((s) => `1.2.840.10008.5.1.4.1.1.${s}`));

export const SC_UNVERIFIED = "Spacing from secondary capture — unverified";

const first = (instance: DicomJsonInstance | undefined, tag: string) => instance?.[tag]?.Value?.[0];
const sopClass = (instance: DicomJsonInstance | undefined) => String(first(instance, TAG.SOPClassUID) ?? "");

export function isSecondaryCapture(instance: DicomJsonInstance | undefined): boolean {
  return SECONDARY_CAPTURE.has(sopClass(instance));
}

const BADGES: Record<string, Omit<CalibrationLegend, "text">> = {
  Calibrated: { badge: "Calibrated", level: "ok" },
  ERMF: { badge: "ERMF", level: "ok" },
  Proj: { badge: "Detector plane (Proj)", level: "warn" },
  "US Region": { badge: "US regions", level: "ok" },
  User: { badge: "User-calibrated", level: "warn" },
  Unknown: { badge: "Unverified", level: "warn" },
  Error: { badge: "Spacing error", level: "warn" },
};

/**
 * Legend for a viewport's raw CS3D length unit (`mm Proj`, `px`, …); undefined for plain
 * tomographic `mm` (CT, MR, PET, WSI), where the spec hides it.
 */
export function calibrationLegend(unit: string, instance?: DicomJsonInstance): CalibrationLegend | undefined {
  const [base, ...rest] = unit.trim().split(" ");
  if (base === "px") return { badge: "No spacing (px)", level: "warn", text: unitTooltip("px") };
  const suffix = rest.join(" ");
  if (suffix === "Unknown" && isSecondaryCapture(instance)) {
    return { badge: "Unverified (SC)", level: "warn", text: SC_UNVERIFIED };
  }
  const badge = BADGES[suffix];
  return badge && { ...badge, text: unitTooltip(unit) };
}

/** SC shim: a secondary capture's PixelSpacing, to be tagged `Unknown`; undefined otherwise. */
export function secondaryCaptureSpacing(
  instance: DicomJsonInstance,
): { rowPixelSpacing: number; columnPixelSpacing: number } | undefined {
  if (!isSecondaryCapture(instance)) return undefined;
  const spacing = instance[TAG.PixelSpacing]?.Value?.map(Number);
  if (spacing?.length !== 2 || !spacing.every((v) => v > 0)) return undefined;
  return { rowPixelSpacing: spacing[0], columnPixelSpacing: spacing[1] };
}

/** Burned-in badge: BurnedInAnnotation=YES, or the tag missing on SC/US. Pixels aren't scrubbed. */
export function burnedInWarning(instance: DicomJsonInstance | undefined): boolean {
  if (!instance) return false;
  const value = first(instance, TAG.BurnedInAnnotation);
  if (value !== undefined) return String(value).toUpperCase() === "YES";
  return isSecondaryCapture(instance) || ULTRASOUND.has(sopClass(instance)) || first(instance, TAG.Modality) === "US";
}
