// Bulk ANN layer on a slide (#292): Microscopy Bulk Simple Annotations rendered read-only through
// dicom-microscopy-viewer's annotation-group layer (OpenLayers vector layers on dmv's map), one
// show/hide per group. dmv's draw/modify/translate interactions are never activated, and the groups
// are not CS3D annotations, so no tool can select, move or delete them.
import { annotationGroups, type BulkAnnotationGroup } from "../../bulk-annotations.ts";
import type { DicomJsonInstance } from "../../series.ts";
import { peerImport } from "./wsi.ts";

/** The dmv VolumeImageViewer members used here (dmv 0.48). */
export interface DmvAnnotationViewer {
  addAnnotationGroups(metadata: unknown): void;
  showAnnotationGroup(uid: string): void;
  hideAnnotationGroup(uid: string): void;
}

type DmvMetadata = { metadata: { MicroscopyBulkSimpleAnnotations: new (options: { metadata: DicomJsonInstance }) => unknown } };

export interface BulkAnnotationLayer {
  add(instances: DicomJsonInstance[]): Promise<void>;
  groups(): BulkAnnotationGroup[];
  setVisible(uid: string, visible: boolean): void;
}

/** `viewer()` returns the slide's dmv viewer (WSIViewport's, set once the slide has opened). */
export function bulkAnnotationLayer(viewer: () => DmvAnnotationViewer, onChange: () => void): BulkAnnotationLayer {
  let groups: BulkAnnotationGroup[] = [];
  return {
    async add(instances) {
      const dmv = (await peerImport("dicom-microscopy-viewer")) as DmvMetadata;
      for (const instance of instances) {
        viewer().addAnnotationGroups(new dmv.metadata.MicroscopyBulkSimpleAnnotations({ metadata: instance }));
        const added = annotationGroups([instance]).filter((g) => !groups.some((known) => known.uid === g.uid));
        added.forEach((g) => viewer().showAnnotationGroup(g.uid)); // dmv adds groups hidden
        groups = [...groups, ...added];
      }
      onChange();
    },
    groups: () => groups.map((g) => ({ ...g })),
    setVisible(uid, visible) {
      const group = groups.find((g) => g.uid === uid);
      if (!group) return;
      if (visible) viewer().showAnnotationGroup(uid);
      else viewer().hideAnnotationGroup(uid);
      groups = groups.map((g) => (g.uid === uid ? { ...g, visible } : g));
      onChange();
    },
  };
}
