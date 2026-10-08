// What the chrome extensions (inspector panels, commands) see of the viewer: state + actions.
// Built fresh by <mires-viewer> on every render; add fields additively.
import type { StackState, StackView, ViewControls, VolumeState } from "./adapter/adapter.ts";
import type { ViewLayout } from "./layout.ts";
import type { Reconstructability } from "./reconstructable.ts";
import type { DicomJsonInstance } from "./series.ts";
import type { BulkAnnotationGroup } from "./bulk-annotations.ts";
import type { Preset, ViewportKind } from "./tools/index.ts";

export interface ViewerContext {
  /** Annotate role (Annotator, PI, Site PI, Admin) on this participant: Arrow, Calibrate, segment tools, Save. */
  canAnnotate: boolean;
  viewport: ViewportKind;
  /** Modality of the series shown (base layer), e.g. "CT"; "" before load. */
  modality: string;
  /** Tool on the left button. */
  activeTool: string;
  /** Controls of the open view; undefined until it is ready. */
  view: ViewControls | undefined;
  stack: StackState | undefined;
  /** The open stack view (calibration #281); undefined for other view kinds or before load. */
  stackView: StackView | undefined;
  /** `/metadata` instance of the image shown (stack); undefined before load. */
  image: DicomJsonInstance | undefined;
  selectTool(toolId: string): void;
  applyPreset(preset: Preset): void;
  /** Stack or volume layout shown (#282). */
  layout: ViewLayout;
  /** Volume state while a volume is shown (#282). */
  volume: VolumeState | undefined;
  /** Whether the series may be shown as a volume (OHIF rule); undefined before load. */
  mpr: Reconstructability | undefined;
  /** Switch layout (stack ↔ volume, orientations); ignored while a switch is running. */
  setLayout(layout: ViewLayout): void;
  /** Groups of the slide's bulk ANN (#292); empty off WSI or without ANN. */
  bulkAnnotationGroups: BulkAnnotationGroup[];
  setBulkAnnotationGroupVisible(uid: string, visible: boolean): void;
}
