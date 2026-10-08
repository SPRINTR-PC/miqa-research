// Volume views (#282): the series cached once as a streaming volume, shown in legacy ORTHOGRAPHIC
// viewports (1 or 3) of one tool group holding every registered tool. Three views: CrosshairsTool
// (viewports added before it is activated; line colours follow orientation) and a VOI synchronizer.
// Fusion (#284) builds on this module. Size guard (#283): `options.decimation` loads a reduced
// (decimatedVolumeLoader) volume; CS3D cache errors while streaming are reported via `options.onTooLarge`.
import {
  Enums,
  eventTarget,
  setVolumesForViewports,
  volumeLoader,
  type RenderingEngine,
  type Types,
} from "@cornerstonejs/core";
import * as csTools from "@cornerstonejs/tools";

import { ORIENTATION_COLOR, type Orientation } from "../../layout.ts";
import { segmentBindings } from "../../tools/segmentation.ts";
import { isTooLargeError, type Decimation } from "../../size-guard.ts";
import type { VoiRange, VolumeLoadStage, VolumeOptions, VolumeState, VolumeView } from "../adapter.ts";
import { addToolsToGroup, applyBindingPlan, registerCornerstoneTool } from "./tools.ts";

export interface VolumeHandle extends VolumeView {
  /** Viewports shown, for the Segmentation (#286). */
  shownViewports(): { kind: "volume"; viewportIds: string[] };
  dispose(): void;
}

const CROSSHAIRS = csTools.CrosshairsTool.toolName;
const FALLBACK_TOOL = csTools.WindowLevelTool.toolName;

const AXIS: Record<Orientation, Enums.OrientationAxis> = {
  axial: Enums.OrientationAxis.AXIAL,
  sagittal: Enums.OrientationAxis.SAGITTAL,
  coronal: Enums.OrientationAxis.CORONAL,
};

/** viewportId → orientation shown, for the crosshair line colours. */
const orientationOf = new Map<string, Orientation>();

registerCornerstoneTool(csTools.CrosshairsTool, {
  configuration: {
    getReferenceLineColor: (viewportId: string) => ORIENTATION_COLOR[orientationOf.get(viewportId) ?? "axial"],
    getReferenceLineControllable: () => true,
    getReferenceLineDraggableRotatable: () => true,
    getReferenceLineSlabThicknessControlsOn: () => false,
  },
});

const ELEMENT_EVENTS = [
  Enums.Events.CAMERA_MODIFIED,
  Enums.Events.VOI_MODIFIED,
  Enums.Events.VOLUME_NEW_IMAGE,
  Enums.Events.IMAGE_RENDERED,
];

interface StreamingVolume {
  load(callback?: () => void): void;
  loadStatus?: { loaded: boolean };
}

/**
 * Cache key of a series' volume: one streaming volume per series, shared by every view; a reduced
 * (decimated, #283) volume is its own cache entry.
 */
export function volumeIdFor(seriesUid: string, decimation?: Decimation): string {
  return decimation ? `decimatedVolumeLoader:${seriesUid}:${decimation.join("-")}` : `cornerstoneStreamingImageVolume:${seriesUid}`;
}

export async function createVolumeView(
  engine: RenderingEngine,
  slots: HTMLDivElement[],
  imageIds: string[],
  seriesUid: string,
  initial: Orientation[],
  onChange: () => void,
  onStage: (stage: VolumeLoadStage) => void,
  { decimation, onTooLarge }: VolumeOptions = {},
): Promise<VolumeHandle> {
  const volumeId = volumeIdFor(seriesUid, decimation);
  const toolGroupId = `tg-vol-${engine.id}`;
  const synchronizerId = `voi-vol-${engine.id}`;
  const viewportId = (slot: number) => `vol-${engine.id}-${slot}`;
  let orientations: Orientation[] = [];
  let shown: string[] = [];
  let group: csTools.Types.IToolGroup | undefined;
  let activeTool = "";

  // First-render stages (#293): the first decimated interleaved pass done, then every slice.
  const onRetrievalStage = (e: Event) => {
    if ((e as CustomEvent<{ stageId: string }>).detail.stageId !== "initialImages") onStage("interleaved");
  };
  // #283: the cache refusing a slice of this volume (CACHE_SIZE_EXCEEDED) while it streams.
  const ownImages = new Set(imageIds);
  let reported = false;
  const onLoadError = (e: Event) => {
    const { imageId, error } = (e as CustomEvent<{ imageId?: string; error?: unknown }>).detail ?? {};
    if (reported || !isTooLargeError(error) || (imageId && !ownImages.has(imageId.split("#")[0]))) return;
    reported = true;
    onTooLarge?.();
  };
  const LOAD_ERRORS = [Enums.Events.IMAGE_LOAD_ERROR, Enums.Events.IMAGE_LOAD_FAILED];
  LOAD_ERRORS.forEach((ev) => eventTarget.addEventListener(ev, onLoadError));
  const stopStageListeners = () => {
    eventTarget.removeEventListener(Enums.Events.IMAGE_RETRIEVAL_STAGE, onRetrievalStage);
    eventTarget.removeEventListener(Enums.Events.IMAGE_VOLUME_LOADING_COMPLETED, onLoaded);
  };
  const loaded = () => {
    stopStageListeners();
    onStage("interleaved");
    onStage("volume-loaded");
  };
  const onLoaded = (e: Event) => {
    if ((e as CustomEvent<{ volumeId: string }>).detail.volumeId === volumeId) loaded();
  };

  const volume = (await volumeLoader
    .createAndCacheVolume(volumeId, { imageIds, ...(decimation ? { ijkDecimation: decimation } : {}) } as never)
    .catch((e: unknown) => {
      LOAD_ERRORS.forEach((ev) => eventTarget.removeEventListener(ev, onLoadError));
      throw e;
    })) as unknown as StreamingVolume;
  if (volume.loadStatus?.loaded) loaded();
  else {
    eventTarget.addEventListener(Enums.Events.IMAGE_RETRIEVAL_STAGE, onRetrievalStage);
    eventTarget.addEventListener(Enums.Events.IMAGE_VOLUME_LOADING_COMPLETED, onLoaded);
    volume.load();
  }

  const viewport = (id: string) => engine.getViewport(id) as Types.IVolumeViewport;
  const all = (fn: (vp: Types.IVolumeViewport) => void) => {
    shown.forEach((id) => fn(viewport(id)));
    engine.renderViewports(shown);
    onChange();
  };

  const applyTool = (toolId: string) => {
    if (!group) return;
    // Crosshairs need several views; a single view falls back to W/L.
    const primary = toolId === CROSSHAIRS && shown.length < 2 ? FALLBACK_TOOL : toolId;
    applyBindingPlan(group, segmentBindings({ primary, viewport: "volume" }));
    // Lines stay visible (and draggable) while another tool is on the left button.
    if (shown.length > 1 && primary !== CROSSHAIRS) group.setToolPassive(CROSSHAIRS);
    activeTool = primary;
    onChange();
  };

  const teardown = () => {
    csTools.ToolGroupManager.destroyToolGroup(toolGroupId);
    csTools.SynchronizerManager.destroySynchronizer(synchronizerId);
    group = undefined;
    shown.forEach((id, slot) => {
      ELEMENT_EVENTS.forEach((e) => slots[slot].removeEventListener(e, onChange));
      engine.disableElement(id);
      orientationOf.delete(id);
    });
    shown = [];
  };

  const show = async (next: Orientation[]) => {
    // Keep the window and invert across re-layouts.
    const keep = shown.length ? viewport(shown[0]).getProperties(volumeId) : undefined;
    teardown();
    orientations = [...next];
    shown = orientations.map((o, slot) => {
      const id = viewportId(slot);
      engine.enableElement({
        viewportId: id,
        type: Enums.ViewportType.ORTHOGRAPHIC,
        element: slots[slot],
        defaultOptions: { orientation: AXIS[o], background: [0, 0, 0] as Types.Point3 },
      });
      orientationOf.set(id, o);
      ELEMENT_EVENTS.forEach((e) => slots[slot].addEventListener(e, onChange));
      return id;
    });
    await setVolumesForViewports(engine, [{ volumeId }], shown);
    if (keep?.voiRange) shown.forEach((id) => viewport(id).setProperties({ voiRange: keep.voiRange, invert: !!keep.invert }, volumeId));

    group = csTools.ToolGroupManager.createToolGroup(toolGroupId)!;
    shown.forEach((id) => group!.addViewport(id, engine.id));
    addToolsToGroup(group);
    const sync = csTools.synchronizers.createVOISynchronizer(synchronizerId, { syncInvertState: true, syncColormap: false });
    shown.forEach((id) => sync.add({ renderingEngineId: engine.id, viewportId: id }));
    applyTool(activeTool || FALLBACK_TOOL);
    engine.renderViewports(shown);
    onChange();
  };

  await show(initial);

  return {
    state(): VolumeState {
      const main = shown[0] ? viewport(shown[0]) : undefined;
      const props = main?.getProperties(volumeId);
      const voi = props?.voiRange;
      return {
        activeTool,
        voi: voi ? { lower: voi.lower, upper: voi.upper } : undefined,
        invert: !!props?.invert,
        views: shown.map((id, slot) => {
          const vp = viewport(id);
          const [x, y, z] = vp.getCamera().focalPoint ?? [0, 0, 0];
          return { orientation: orientations[slot], focalPoint: [x, y, z], sliceIndex: vp.getSliceIndex(), sliceCount: vp.getNumberOfSlices() };
        }),
      };
    },
    setOrientations: show,
    setTool: applyTool,
    shownViewports: () => ({ kind: "volume", viewportIds: [...shown] }),
    setVoi(voi: VoiRange) {
      all((vp) => vp.setProperties({ voiRange: voi }, volumeId));
    },
    resetVoi() {
      all((vp) => {
        const invert = vp.getProperties(volumeId)?.invert;
        vp.resetProperties(volumeId);
        vp.setProperties({ invert }, volumeId);
      });
    },
    toggleInvert() {
      all((vp) => vp.setProperties({ invert: !vp.getProperties(volumeId)?.invert }, volumeId));
    },
    resetView() {
      all((vp) => {
        vp.resetCamera();
        vp.resetProperties(volumeId);
      });
      applyTool(activeTool); // re-centres the crosshairs on the reset cameras
    },
    dispose() {
      stopStageListeners();
      LOAD_ERRORS.forEach((ev) => eventTarget.removeEventListener(ev, onLoadError));
      teardown();
    },
  };
}
