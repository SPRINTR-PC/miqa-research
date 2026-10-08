// Whether a series can be shown as a volume (MPR, three views, fusion): OHIF's
// isDisplaySetReconstructable rule (OHIF 3.x, spec #271 / research #187). Pure, no CS3D.
//   CT/MR/PT/NM · more than one image · every slice has a position · same rows, columns,
//   samples and orientation · spacing equal within 20% (whole missing slices allowed, as in OHIF).
//   Multi-frame: needs shared pixel measures (SharedFunctionalGroups › PixelMeasures).
import type { DicomJsonInstance, LoadedSeries } from "./series.ts";

export type Reconstructability = { ok: true } | { ok: false; reason: string };

const MODALITIES = ["CT", "MR", "PT", "NM"];
const TOLERANCE = 0.2;
const ORIENTATION_TOLERANCE = 0.01;

const TAG = {
  Modality: "00080060",
  ImagePositionPatient: "00200032",
  ImageOrientationPatient: "00200037",
  Rows: "00280010",
  Columns: "00280011",
  SamplesPerPixel: "00280002",
  NumberOfFrames: "00280008",
  SharedFunctionalGroups: "52009229",
  PixelMeasures: "00289110",
} as const;

const value = (i: DicomJsonInstance, tag: string) => i[tag]?.Value;
const num = (i: DicomJsonInstance, tag: string) => Number(value(i, tag)?.[0]);
const vec = (i: DicomJsonInstance, tag: string) => value(i, tag)?.map(Number);

function normal(iop: number[]): number[] {
  const [rx, ry, rz, cx, cy, cz] = iop;
  return [ry * cz - rz * cy, rz * cx - rx * cz, rx * cy - ry * cx];
}

const dot = (a: number[], b: number[]) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];

function sameOrientation(a: number[] | undefined, b: number[] | undefined): boolean {
  return !!a && !!b && a.length === 6 && b.length === 6 && a.every((v, k) => Math.abs(v - b[k]) < ORIENTATION_TOLERANCE);
}

const no = (reason: string): Reconstructability => ({ ok: false, reason });

export function isReconstructable(series: LoadedSeries): Reconstructability {
  const instances = [...new Set(series.images.map((i) => i.instance))];
  const first = instances[0];
  if (!first) return no("Series has no images");
  const modality = String(value(first, TAG.Modality)?.[0] ?? "");
  if (!MODALITIES.includes(modality)) return no(`${modality || "This"} series can't be reconstructed`);

  if (num(first, TAG.NumberOfFrames) > 1) {
    const shared = value(first, TAG.SharedFunctionalGroups)?.[0] as DicomJsonInstance | undefined;
    return shared?.[TAG.PixelMeasures]?.Value?.length ? { ok: true } : no("Multi-frame image without shared pixel measures");
  }
  if (instances.length < 2) return no("A single image can't be reconstructed");
  if (!instances.every((i) => vec(i, TAG.ImagePositionPatient)?.length === 3)) return no("Some images have no position");

  const iop = vec(first, TAG.ImageOrientationPatient);
  const same = (i: DicomJsonInstance) =>
    num(i, TAG.Rows) === num(first, TAG.Rows) &&
    num(i, TAG.Columns) === num(first, TAG.Columns) &&
    num(i, TAG.SamplesPerPixel) === num(first, TAG.SamplesPerPixel) &&
    sameOrientation(vec(i, TAG.ImageOrientationPatient), iop);
  if (!instances.every(same)) return no("Images differ in size, samples or orientation");

  const n = normal(iop!);
  const positions = instances.map((i) => dot(vec(i, TAG.ImagePositionPatient)!, n)).sort((a, b) => a - b);
  if (positions.length > 2) {
    const average = (positions[positions.length - 1] - positions[0]) / (positions.length - 1);
    for (let k = 1; k < positions.length; k++) {
      const spacing = positions[k] - positions[k - 1];
      if (Math.abs(spacing - average) < average * TOLERANCE) continue;
      const slices = Math.round(spacing / average);
      const missingSlices = slices >= 1 && Math.abs(spacing - slices * average) / slices < average * TOLERANCE;
      if (!missingSlices) return no("Slice spacing is irregular");
    }
  }
  return { ok: true };
}
