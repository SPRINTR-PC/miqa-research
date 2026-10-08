// SUV (#284, spec "Three views and fusion"): PET is shown in SUVbw via @cornerstonejs/calculate-suv
// (whole series, adapter/cornerstone/suv.ts). A missing input makes CS3D fall back to raw Bq/ml
// silently, so the UI flags it. Pure: which inputs a series has, and why scaling can't apply.
import type { DicomJsonInstance, LoadedSeries } from "./series.ts";

/** calculate-suv's per-instance input (its `InstanceMetadata`). */
export interface SuvInput {
  CorrectedImage: string[];
  Units: string;
  RadionuclideHalfLife: number;
  RadionuclideTotalDose: number;
  RadiopharmaceuticalStartTime?: string;
  RadiopharmaceuticalStartDateTime?: string;
  DecayCorrection: string;
  PatientWeight: number;
  PatientSize?: number;
  PatientSex?: string;
  SeriesDate: string;
  SeriesTime: string;
  AcquisitionDate: string;
  AcquisitionTime: string;
  FrameReferenceTime?: number;
  ActualFrameDuration?: number;
}

/** Whether a PET series is shown in SUV (`applied`) or raw Bq/ml, and why. Undefined off PET. */
export type SuvStatus = { applied: true } | { applied: false; reason: string };

const TAG = {
  Modality: "00080060",
  SeriesDate: "00080021",
  AcquisitionDate: "00080022",
  SeriesTime: "00080031",
  AcquisitionTime: "00080032",
  PatientSex: "00100040",
  PatientSize: "00101020",
  PatientWeight: "00101030",
  ActualFrameDuration: "00181242",
  CorrectedImage: "00280051",
  Units: "00541001",
  RadiopharmaceuticalInformationSequence: "00540016",
  FrameReferenceTime: "00541300",
  DecayCorrection: "00541102",
  RadiopharmaceuticalStartTime: "00181072",
  RadionuclideTotalDose: "00181074",
  RadionuclideHalfLife: "00181075",
  RadiopharmaceuticalStartDateTime: "00181078",
} as const;

const first = (i: DicomJsonInstance, tag: string): unknown => i[tag]?.Value?.[0];
const text = (i: DicomJsonInstance, tag: string) => {
  const v = first(i, tag);
  return v === undefined || v === null || v === "" ? undefined : String(v);
};
const number = (i: DicomJsonInstance, tag: string) => {
  const raw = first(i, tag);
  const v = Number(raw);
  return raw === undefined || raw === null || raw === "" || !Number.isFinite(v) ? undefined : v;
};

export function isPet(series: LoadedSeries): boolean {
  return text(series.images[0]?.instance ?? {}, TAG.Modality) === "PT";
}

/** calculate-suv inputs per instance, or the reason (missing tags, units) SUV can't be computed. */
export function suvInputs(instances: DicomJsonInstance[]): { ok: true; inputs: SuvInput[] } | { ok: false; reason: string } {
  const missing = new Set<string>();
  const inputs = instances.map((i) => {
    const need = <T>(name: string, v: T | undefined): T => {
      if (v === undefined) missing.add(name);
      return v as T;
    };
    const rp = first(i, TAG.RadiopharmaceuticalInformationSequence) as DicomJsonInstance | undefined;
    if (!rp) missing.add("RadiopharmaceuticalInformationSequence");
    const startTime = rp && text(rp, TAG.RadiopharmaceuticalStartTime);
    const startDateTime = rp && text(rp, TAG.RadiopharmaceuticalStartDateTime);
    if (rp && !startTime && !startDateTime) missing.add("RadiopharmaceuticalStartTime");
    const corrected = i[TAG.CorrectedImage]?.Value?.map(String);
    const input: SuvInput = {
      CorrectedImage: need("CorrectedImage", corrected?.length ? corrected : undefined),
      Units: need("Units", text(i, TAG.Units)),
      RadionuclideHalfLife: rp ? need("RadionuclideHalfLife", number(rp, TAG.RadionuclideHalfLife)) : NaN,
      RadionuclideTotalDose: rp ? need("RadionuclideTotalDose", number(rp, TAG.RadionuclideTotalDose)) : NaN,
      ...(startTime ? { RadiopharmaceuticalStartTime: startTime } : {}),
      ...(startDateTime ? { RadiopharmaceuticalStartDateTime: startDateTime } : {}),
      DecayCorrection: need("DecayCorrection", text(i, TAG.DecayCorrection)),
      PatientWeight: need("PatientWeight", number(i, TAG.PatientWeight)),
      SeriesDate: need("SeriesDate", text(i, TAG.SeriesDate)),
      SeriesTime: need("SeriesTime", text(i, TAG.SeriesTime)),
      AcquisitionDate: need("AcquisitionDate", text(i, TAG.AcquisitionDate)),
      AcquisitionTime: need("AcquisitionTime", text(i, TAG.AcquisitionTime)),
    };
    const optional = {
      PatientSize: number(i, TAG.PatientSize),
      // Only SUVlbm uses it, and calculate-suv throws on anything but M/F (O is valid DICOM).
      PatientSex: ["M", "F"].includes(text(i, TAG.PatientSex) ?? "") ? text(i, TAG.PatientSex) : undefined,
      FrameReferenceTime: number(i, TAG.FrameReferenceTime),
      ActualFrameDuration: number(i, TAG.ActualFrameDuration),
    };
    for (const [k, v] of Object.entries(optional)) if (v !== undefined) Object.assign(input, { [k]: v });
    return input;
  });
  if (missing.size) return { ok: false, reason: `missing ${[...missing].sort().join(", ")}` };
  const units = inputs.find((i) => i.Units !== "BQML")?.Units;
  if (units) return { ok: false, reason: `Units are ${units}, not BQML` };
  return { ok: true, inputs };
}

/** The series' instances once each (frames of a multi-frame instance share one). */
export function seriesInstances(series: LoadedSeries): DicomJsonInstance[] {
  return [...new Set(series.images.map((im) => im.instance))];
}

/**
 * Expected SUV status from /metadata alone (the stub adapter's answer; the CS3D adapter also checks
 * that CS3D's scaling module really carries `suvbw`).
 */
export function suvStatusFor(series: LoadedSeries): SuvStatus | undefined {
  if (!isPet(series)) return undefined;
  const r = suvInputs(seriesInstances(series));
  return r.ok ? { applied: true } : { applied: false, reason: r.reason };
}

/** Warning text for a PET series shown in Bq/ml; undefined when SUV applies or off PET. */
export function suvWarning(status: SuvStatus | undefined): string | undefined {
  return status && !status.applied ? `Bq/ml, not SUV: SUV scaling wasn't applied (${status.reason}).` : undefined;
}
