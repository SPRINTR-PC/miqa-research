// What the chrome extensions (inspector panels, commands) see of the viewer: state + actions.
// Built fresh by <mires-viewer> on every render; add fields additively.
import type { StackState, ViewControls } from "./adapter/adapter.ts";
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
  selectTool(toolId: string): void;
  applyPreset(preset: Preset): void;
  /** Groups of the slide's bulk ANN (#292); empty off WSI or without ANN. */
  bulkAnnotationGroups: BulkAnnotationGroup[];
  setBulkAnnotationGroupVisible(uid: string, visible: boolean): void;
}
