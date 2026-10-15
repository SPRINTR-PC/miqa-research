// DICOM JSON fixtures shared by viewer unit tests (not a test file itself).
import type { DicomJsonInstance } from "./series.ts";
import type { SeriesEntry } from "./chrome/series-list.ts";

/** A PET instance with every SUV input (BQML, decay-corrected to START); `undefined` in overrides removes a tag. */
export function petInstance(overrides: Record<string, unknown> = {}): DicomJsonInstance {
  const tags: DicomJsonInstance = {
    "00080060": { vr: "CS", Value: ["PT"] },
    "00080021": { vr: "DA", Value: ["20260101"] },
    "00080031": { vr: "TM", Value: ["120000"] },
    "00080022": { vr: "DA", Value: ["20260101"] },
    "00080032": { vr: "TM", Value: ["120000"] },
    "00101030": { vr: "DS", Value: [75] },
    "00541001": { vr: "LO", Value: ["BQML"] },
    "00280051": { vr: "CS", Value: ["ATTN", "DECY"] },
    "00541102": { vr: "CS", Value: ["START"] },
    "00540016": {
      vr: "SQ",
      Value: [
        {
          "00181072": { vr: "TM", Value: ["110000"] },
          "00181074": { vr: "DS", Value: [370000000] },
          "00181075": { vr: "DS", Value: [6586.2] },
        },
      ],
    },
  };
  for (const [tag, value] of Object.entries(overrides)) {
    if (value === undefined) delete tags[tag];
    else tags[tag] = value as DicomJsonInstance[string];
  }
  return tags;
}

export interface VolumeFixture {
  modality?: string;
  frameOfReference?: string;
  size?: number;
  description?: string;
  /** Extra tags per instance (e.g. petInstance() for SUV inputs). */
  extra?: DicomJsonInstance;
}

/** A reconstructable volume series: `n` axial slices 2.5 mm apart. */
export function volumeInstances(n: number, { modality = "CT", frameOfReference = "2.25.4", size = 64, description, extra = {} }: VolumeFixture = {}) {
  return Array.from({ length: n }, (_, i) => ({
    ...extra,
    "00080018": { vr: "UI", Value: [`2.25.${modality}.${i + 1}`] },
    "00080060": { vr: "CS", Value: [modality] },
    ...(description ? { "0008103E": { vr: "LO", Value: [description] } } : {}),
    "00200013": { vr: "IS", Value: [i + 1] },
    "00200032": { vr: "DS", Value: [0, 0, i * 2.5] },
    "00200037": { vr: "DS", Value: [1, 0, 0, 0, 1, 0] },
    "00200052": { vr: "UI", Value: [frameOfReference] },
    "00280010": { vr: "US", Value: [size] },
    "00280011": { vr: "US", Value: [size] },
    "00280002": { vr: "US", Value: [1] },
    "00280100": { vr: "US", Value: [16] },
  })) as DicomJsonInstance[];
}

/** The page's series list (#279) for element tests: `open` series (first = base), then `related`. */
export function seriesEntries(
  open: string[],
  related: string[] = [],
  study = "2.25.100",
  details: Record<string, Partial<SeriesEntry>> = {},
): SeriesEntry[] {
  const entry = (series: string, isOpen: boolean): SeriesEntry => ({
    study, series, modality: "", description: "", instances: 0, frame_of_reference: null, ...details[series], open: isOpen,
  });
  return [...open.map((uid) => entry(uid, true)), ...related.map((uid) => entry(uid, false))];
}
