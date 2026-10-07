// Series loading from our WADO-RS: /metadata (DICOM JSON) → ordered wadors frame imageIds.
// Pure fetch + data shaping; no Cornerstone3D import, so it runs under vitest/happy-dom.

/** One DICOM JSON instance (PS3.18 F.2), as served by `/series/{uid}/metadata`. */
export type DicomJsonInstance = Record<string, { vr: string; Value?: unknown[] }>;

export interface SeriesRef {
  /** WADO-RS root, e.g. `/api/v1/dicom` (no trailing slash). */
  wadoRoot: string;
  studyUid: string;
  seriesUid: string;
}

export interface SeriesImage {
  /** `wadors:<root>/studies/../series/../instances/<sop>/frames/<n>` */
  imageId: string;
  /** The instance this frame belongs to; shared by all frames of a multi-frame instance. */
  instance: DicomJsonInstance;
}

export interface LoadedSeries {
  ref: SeriesRef;
  images: SeriesImage[];
}

export class SeriesLoadError extends Error {
  readonly status: number | undefined;

  constructor(status?: number, message?: string) {
    super(message ?? (status ? `Series metadata request failed (HTTP ${status})` : "Series has no images"));
    this.name = "SeriesLoadError";
    this.status = status;
  }
}

const TAG = {
  SOPInstanceUID: "00080018",
  InstanceNumber: "00200013",
  ImagePositionPatient: "00200032",
  ImageOrientationPatient: "00200037",
  NumberOfFrames: "00280008",
} as const;

function values(instance: DicomJsonInstance, tag: string): unknown[] | undefined {
  return instance[tag]?.Value;
}

function numbers(instance: DicomJsonInstance, tag: string): number[] | undefined {
  const v = values(instance, tag);
  return v?.map(Number);
}

/** Position along the slice normal, or undefined without full geometry. */
function slicePosition(instance: DicomJsonInstance): number | undefined {
  const iop = numbers(instance, TAG.ImageOrientationPatient);
  const ipp = numbers(instance, TAG.ImagePositionPatient);
  if (iop?.length !== 6 || ipp?.length !== 3) return undefined;
  const [rx, ry, rz, cx, cy, cz] = iop;
  const normal = [ry * cz - rz * cy, rz * cx - rx * cz, rx * cy - ry * cx];
  return normal[0] * ipp[0] + normal[1] * ipp[1] + normal[2] * ipp[2];
}

function sortInstances(instances: DicomJsonInstance[]): DicomJsonInstance[] {
  const positions = instances.map(slicePosition);
  if (positions.every((p) => p !== undefined)) {
    return instances
      .map((instance, i) => ({ instance, key: positions[i] as number }))
      .sort((a, b) => a.key - b.key)
      .map((e) => e.instance);
  }
  const n = (i: DicomJsonInstance) => numbers(i, TAG.InstanceNumber)?.[0] ?? 0;
  return [...instances].sort((a, b) => n(a) - n(b));
}

export function seriesUrl(ref: SeriesRef): string {
  return `${ref.wadoRoot}/studies/${ref.studyUid}/series/${ref.seriesUid}`;
}

/** Fetch a series' `/metadata` with the session cookie and shape it into ordered frame imageIds. */
export async function fetchSeries(ref: SeriesRef): Promise<LoadedSeries> {
  const response = await fetch(`${seriesUrl(ref)}/metadata`, {
    credentials: "same-origin",
    headers: { Accept: "application/dicom+json" },
  });
  if (!response.ok) throw new SeriesLoadError(response.status);
  const instances = (await response.json()) as DicomJsonInstance[];
  if (!instances.length) throw new SeriesLoadError();

  const images = sortInstances(instances).flatMap((instance) => {
    const sop = String(values(instance, TAG.SOPInstanceUID)?.[0]);
    const frames = numbers(instance, TAG.NumberOfFrames)?.[0] ?? 1;
    return Array.from({ length: frames }, (_, f) => ({
      imageId: `wadors:${seriesUrl(ref)}/instances/${sop}/frames/${f + 1}`,
      instance,
    }));
  });
  return { ref, images };
}
