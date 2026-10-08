// Bulk ANN on a slide (#292): Microscopy Bulk Simple Annotations (algorithm output) shown read-only
// through dicom-microscopy-viewer's annotation-group layer, toggled per group. Pure parts, no CS3D:
// finding the slide's ANN (viewer object list → WADO /metadata) and reading its groups.
// The layer itself is adapter/cornerstone/bulk-annotations.ts.
import type { DicomJsonInstance, SeriesRef } from "./series.ts";

/** Microscopy Bulk Simple Annotations Storage. */
export const ANN_SOP_CLASS = "1.2.840.10008.5.1.4.1.1.91.1";

/** One annotation group of an ANN instance, as the inspector lists it. */
export interface BulkAnnotationGroup {
  /** AnnotationGroupUID; dmv's group id. */
  uid: string;
  /** Property type (e.g. "Neoplasm"); the group label is scrubbed by the De-identification Profile. */
  name: string;
  graphicType: string;
  count: number;
  visible: boolean;
}

const TAG = {
  SOPClassUID: "00080016",
  AnnotationGroupSequence: "006A0002",
  AnnotationGroupUID: "006A0003",
  AnnotationGroupNumber: "0040A180",
  AnnotationPropertyTypeCodeSequence: "006A000A",
  CodeMeaning: "00080104",
  NumberOfAnnotations: "006A000C",
  GraphicType: "00700023",
} as const;

const first = (item: DicomJsonInstance | undefined, tag: string) => item?.[tag]?.Value?.[0];

/** Groups of ANN instances, in instance then group order, all shown. */
export function annotationGroups(instances: DicomJsonInstance[]): BulkAnnotationGroup[] {
  return instances.flatMap((instance) =>
    ((instance[TAG.AnnotationGroupSequence]?.Value ?? []) as DicomJsonInstance[]).map((item) => {
      const type = first(item, TAG.AnnotationPropertyTypeCodeSequence) as DicomJsonInstance | undefined;
      return {
        uid: String(first(item, TAG.AnnotationGroupUID)),
        name: String(first(type, TAG.CodeMeaning) ?? `Group ${first(item, TAG.AnnotationGroupNumber) ?? ""}`.trim()),
        graphicType: String(first(item, TAG.GraphicType) ?? ""),
        count: Number(first(item, TAG.NumberOfAnnotations) ?? 0),
        visible: true,
      };
    }),
  );
}

export interface BulkAnnotationSource {
  /** Viewer API root, e.g. `/api/v1/viewer`. */
  apiRoot: string;
  /** Study Participant id: the object list is per participant. */
  participant: string;
}

/** A chain from the viewer object list (subset of the API's ChainOut). */
interface ObjectChain {
  modality: string | null;
  series_instance_uid: string;
}

async function getJson<T>(url: string): Promise<T> {
  const response = await fetch(url, { credentials: "same-origin", headers: { Accept: "application/json" } });
  if (!response.ok) throw new Error(`Bulk annotations request failed (HTTP ${response.status})`);
  return (await response.json()) as T;
}

/**
 * The current ANN instances made on `slide`: chain heads from the object list (blinding and
 * visibility applied server-side), then each ANN series' sanitized `/metadata`, whose point
 * coordinates come inline (InlineBinary), so dmv needs no BulkData endpoint.
 */
export async function fetchBulkAnnotations(source: BulkAnnotationSource, slide: SeriesRef): Promise<DicomJsonInstance[]> {
  const query = new URLSearchParams({ participant: source.participant, series: slide.seriesUid });
  const chains = await getJson<ObjectChain[]>(`${source.apiRoot}/objects?${query}`);
  const series = chains.filter((c) => c.modality === "ANN").map((c) => c.series_instance_uid);
  const instances = await Promise.all(
    series.map((uid) => getJson<DicomJsonInstance[]>(`${slide.wadoRoot}/studies/${slide.studyUid}/series/${uid}/metadata`)),
  );
  return instances.flat().filter((i) => first(i, TAG.SOPClassUID) === ANN_SOP_CLASS);
}
