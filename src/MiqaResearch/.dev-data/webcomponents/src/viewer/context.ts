// What the chrome extensions (inspector panels, commands) see of the viewer: state + actions.
// Built fresh by <mires-viewer> on every render; add fields additively.
import type { LayerState, SegmentationView, StackState, StackView, ViewControls, VolumeState } from "./adapter/adapter.ts";
import type { LayerDisplay } from "./fusion.ts";
import type { SegmentationState, ValueRange } from "./segmentation.ts";
import type { SuvStatus } from "./suv.ts";
import type { ViewLayout } from "./layout.ts";
import type { Reconstructability } from "./reconstructable.ts";
import type { DicomJsonInstance } from "./series.ts";
import type { BulkAnnotationGroup } from "./bulk-annotations.ts";
import type { GpuLimits, SizeGuard, VolumeFit } from "./size-guard.ts";
import type { Preset, ViewportKind } from "./tools/index.ts";

export interface ViewerContext {
  /** Annotate role (Annotator, PI, Site PI, Admin) on this participant: Arrow, Calibrate, segment tools, Save. */
  canAnnotate: boolean;
  viewport: ViewportKind;
  /** Modality of the series shown (the selected layer when fused, #284), e.g. "CT"; "" before load. Picks the presets. */
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
  /** Size guard (#283): the 2.5 GiB budget ledger; fusion (#284) and labelmaps (#286) check/reserve/release here. */
  budget: SizeGuard;
  /** WebGL limits; undefined before load. */
  gpu: GpuLimits | undefined;
  /** Whether the series fits as a full-resolution volume; undefined before load or when not reconstructable. */
  volumeFit: VolumeFit | undefined;
  /** Show a refusal message (dismissible) over the view, e.g. an over-budget fusion or labelmap. */
  refuse(message: string): void;
  /** Segmentation (#286) on the base series; undefined until a segment tool or "New segmentation" makes it. */
  segmentation: SegmentationState | undefined;
  segmentationView: SegmentationView | undefined;
  /** Make the Segmentation if there is none (size guard first); undefined, with a refusal shown, when it doesn't fit. */
  ensureSegmentation(): Promise<SegmentationView | undefined>;
  /** The layer threshold runs on: the selected layer (#284), else the base series. */
  thresholdLayer: { seriesUid: string; modality: string };
  /** Run the threshold on `thresholdLayer`; the voxels set end up in `thresholdResult`. */
  runThreshold(range: ValueRange, slices: number): void;
  thresholdResult: number | undefined;
  /** Fusion (#284): layers of the volume view, base first; empty off volumes. */
  layers: LayerState[];
  /** Series UID of the selected layer (right-drag W/L, presets); undefined off volumes. */
  selectedLayer: string | undefined;
  selectLayer(seriesUid: string): void;
  setLayerDisplay(seriesUid: string, change: Partial<LayerDisplay>): void;
  /** Remove a fused overlay (releases its budget). */
  removeLayer(seriesUid: string): void;
  /** SUV status of the series shown (PET); undefined otherwise. */
  suv: SuvStatus | undefined;
}
