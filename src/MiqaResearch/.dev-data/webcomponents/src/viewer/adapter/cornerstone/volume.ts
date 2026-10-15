// Volume views (#282): the series cached once as a streaming volume, shown in legacy ORTHOGRAPHIC
// viewports (1 or 3) of one tool group holding every registered tool. Three views: CrosshairsTool
// (viewports added before it is activated; line colours follow orientation) and a VOI synchronizer.
// Size guard (#283): `options.decimation` loads a reduced (decimatedVolumeLoader) volume; CS3D cache
// errors while streaming are reported via `options.onTooLarge`.
// Fusion (#284): overlays are more volumes in the same viewports (base first), each with its own
// window, colormap and opacity curve (./fusion.ts); the selected overlay gets right-drag W/L.
import {
  Enums,
  addVolumesToViewports,
  eventTarget,
  setVolumesForViewports,
  volumeLoader,
  type RenderingEngine,
  type Types,
} from "@cornerstonejs/core";
import * as csTools from "@cornerstonejs/tools";

import { dragWindow, layerDisplay, modalityOf, seriesLabel, type LayerDisplay } from "../../fusion.ts";
import { ORIENTATION_COLOR, type Orientation } from "../../layout.ts";
import { segmentBindings } from "../../tools/segmentation.ts";
import type { LoadedSeries } from "../../series.ts";
import { isTooLargeError, type Decimation } from "../../size-guard.ts";
import type { SuvStatus } from "../../suv.ts";
import type { LayerOptions, LayerState, VoiRange, VolumeLoadStage, VolumeOptions, VolumeState, VolumeView } from "../adapter.ts";
import { colormapProperties, LAYER_WINDOW_LEVEL, setLayerWindowHandler } from "./fusion.ts";
import { registerSeriesMetadata } from "./metadata.ts";
import { suvStatusOf } from "./suv.ts";
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

const LOAD_ERRORS = [Enums.Events.IMAGE_LOAD_ERROR, Enums.Events.IMAGE_LOAD_FAILED];

interface StreamingVolume {
  load(callback?: () => void): void;
  loadStatus?: { loaded: boolean };
}

/** One series shown in the views: the base (layers[0]) or a fused overlay. */
interface Layer {
  seriesUid: string;
  volumeId: string;
  label: string;
  modality: string;
  display: LayerDisplay;
  suv: SuvStatus | undefined;
  /** Window it was added with (resetVoi goes back to it); undefined = CS3D's default. */
  voi: VoiRange | undefined;
  /** Base only: a colormap was picked (else CS3D's default grey ramp stays). */
  styled: boolean;
  dispose(): void;
}

/**
 * Cache key of a series' volume: one streaming volume per series, shared by every view; a reduced
 * (decimated, #283) volume is its own cache entry.
 */
export function volumeIdFor(seriesUid: string, decimation?: Decimation): string {
  return decimation ? `decimatedVolumeLoader:${seriesUid}:${decimation.join("-")}` : `cornerstoneStreamingImageVolume:${seriesUid}`;
}

/** Report CACHE_SIZE_EXCEEDED for one of `imageIds` once; returns the unsubscribe. */
function onCacheRefusal(imageIds: string[], report: () => void): () => void {
  const own = new Set(imageIds);
  let reported = false;
  const listener = (e: Event) => {
    const { imageId, error } = (e as CustomEvent<{ imageId?: string; error?: unknown }>).detail ?? {};
    if (reported || !isTooLargeError(error) || (imageId && !own.has(imageId.split("#")[0]))) return;
    reported = true;
    report();
  };
  LOAD_ERRORS.forEach((ev) => eventTarget.addEventListener(ev, listener));
  return () => LOAD_ERRORS.forEach((ev) => eventTarget.removeEventListener(ev, listener));
}

export async function createVolumeView(
  engine: RenderingEngine,
  slots: HTMLDivElement[],
  imageIds: string[],
  series: LoadedSeries,
  initial: Orientation[],
  onChange: () => void,
  onStage: (stage: VolumeLoadStage) => void,
  { decimation, onTooLarge }: VolumeOptions = {},
): Promise<VolumeHandle> {
  const seriesUid = series.ref.seriesUid;
  const volumeId = volumeIdFor(seriesUid, decimation);
  const toolGroupId = `tg-vol-${engine.id}`;
  const synchronizerId = `voi-vol-${engine.id}`;
  const viewportId = (slot: number) => `vol-${engine.id}-${slot}`;
  let orientations: Orientation[] = [];
  let shown: string[] = [];
  let group: csTools.Types.IToolGroup | undefined;
  let activeTool = "";
  let sync: csTools.Synchronizer | undefined;

  // First-render stages (#293): the first decimated interleaved pass done, then every slice.
  const onRetrievalStage = (e: Event) => {
    if ((e as CustomEvent<{ stageId: string }>).detail.stageId !== "initialImages") onStage("interleaved");
  };
  // #283: the cache refusing a slice of this volume (CACHE_SIZE_EXCEEDED) while it streams.
  const stopBaseRefusal = onCacheRefusal(imageIds, () => onTooLarge?.());
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
      stopBaseRefusal();
      throw e;
    })) as unknown as StreamingVolume;
  if (volume.loadStatus?.loaded) loaded();
  else {
    eventTarget.addEventListener(Enums.Events.IMAGE_RETRIEVAL_STAGE, onRetrievalStage);
    eventTarget.addEventListener(Enums.Events.IMAGE_VOLUME_LOADING_COMPLETED, onLoaded);
    volume.load();
  }

  const layers: Layer[] = [
    {
      seriesUid,
      volumeId,
      label: seriesLabel(series),
      modality: modalityOf(series),
      display: layerDisplay(modalityOf(series), { base: true }),
      suv: suvStatusOf(seriesUid),
      voi: undefined,
      styled: false,
      dispose: stopBaseRefusal,
    },
  ];
  let selected = seriesUid;
  const base = () => layers[0];
  const layerOf = (uid: string) => layers.find((l) => l.seriesUid === uid);
  const selectedLayer = () => layerOf(selected) ?? base();

  const viewport = (id: string) => engine.getViewport(id) as Types.IVolumeViewport;
  const render = () => {
    engine.renderViewports(shown);
    onChange();
  };
  const all = (fn: (vp: Types.IVolumeViewport) => void) => {
    shown.forEach((id) => fn(viewport(id)));
    render();
  };
  const layerVoi = (l: Layer) => (shown[0] ? viewport(shown[0]).getProperties(l.volumeId)?.voiRange : undefined);
  const setLayerVoi = (l: Layer, voi: VoiRange) => shown.forEach((id) => viewport(id).setProperties({ voiRange: voi }, l.volumeId));
  const applyDisplay = (l: Layer) => {
    if (l === base() && !l.styled) return;
    shown.forEach((id) => viewport(id).setProperties({ colormap: colormapProperties(l.display) } as never, l.volumeId));
  };

  // Right-drag on an overlay: CS3D's WindowLevelTool would window the base (the first volume).
  const windowSelectedOverlay = (dx: number, dy: number) => {
    const l = selectedLayer();
    const voi = layerVoi(l);
    if (l === base() || !voi) return;
    setLayerVoi(l, dragWindow(voi, dx, dy));
    render();
  };

  const applyTool = (toolId: string) => {
    if (!group) return;
    // Crosshairs need several views; a single view falls back to W/L.
    const primary = toolId === CROSSHAIRS && shown.length < 2 ? FALLBACK_TOOL : toolId;
    // Right-drag: a segment tool's erase twin wins; else the selected overlay's W/L (#284); else W/L.
    const overlay = selectedLayer() !== base();
    applyBindingPlan(group, segmentBindings({ primary, viewport: "volume", ...(overlay ? { secondary: LAYER_WINDOW_LEVEL } : {}) }));
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
      setLayerWindowHandler(id, undefined);
    });
    shown = [];
  };

  const show = async (next: Orientation[]) => {
    // Keep every layer's window, and the base's invert, across re-layouts.
    const keep = new Map(layers.map((l) => [l.volumeId, shown.length ? viewport(shown[0]).getProperties(l.volumeId) : undefined]));
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
      setLayerWindowHandler(id, windowSelectedOverlay);
      return id;
    });
    await setVolumesForViewports(engine, layers.map((l) => ({ volumeId: l.volumeId })), shown);
    layers.forEach((l, i) => {
      applyDisplay(l);
      const kept = keep.get(l.volumeId);
      const voi = kept?.voiRange ?? l.voi;
      if (i === 0 && kept?.voiRange) shown.forEach((id) => viewport(id).setProperties({ voiRange: kept.voiRange, invert: !!kept.invert }, l.volumeId));
      else if (voi) setLayerVoi(l, voi);
    });

    group = csTools.ToolGroupManager.createToolGroup(toolGroupId)!;
    shown.forEach((id) => group!.addViewport(id, engine.id));
    addToolsToGroup(group);
    const voiSync = (sync = csTools.synchronizers.createVOISynchronizer(synchronizerId, { syncInvertState: true, syncColormap: false }));
    shown.forEach((id) => voiSync.add({ renderingEngineId: engine.id, viewportId: id }));
    applyTool(activeTool || FALLBACK_TOOL);
    render();
  };

  await show(initial);

  const layerState = (l: Layer): LayerState => {
    const voi = layerVoi(l);
    return {
      seriesUid: l.seriesUid,
      label: l.label,
      modality: l.modality,
      ...l.display,
      curve: l.display.curve.map((p) => ({ ...p })),
      voi: voi ? { lower: voi.lower, upper: voi.upper } : undefined,
      ...(l.suv ? { suv: l.suv } : {}),
    };
  };

  return {
    state(): VolumeState {
      const states = shown.length ? layers.map(layerState) : [];
      const props = shown[0] ? viewport(shown[0]).getProperties(volumeId) : undefined;
      return {
        activeTool,
        voi: states.find((l) => l.seriesUid === selected)?.voi,
        invert: !!props?.invert,
        views: shown.map((id, slot) => {
          const vp = viewport(id);
          const [x, y, z] = vp.getCamera().focalPoint ?? [0, 0, 0];
          return { orientation: orientations[slot], focalPoint: [x, y, z], sliceIndex: vp.getSliceIndex(), sliceCount: vp.getNumberOfSlices() };
        }),
        layers: states,
        selectedLayer: selected,
      };
    },
    setOrientations: show,
    setTool: applyTool,
    shownViewports: () => ({ kind: "volume", viewportIds: [...shown] }),
    setVoi(voi: VoiRange) {
      const l = selectedLayer();
      all((vp) => vp.setProperties({ voiRange: voi }, l.volumeId));
    },
    resetVoi() {
      const l = selectedLayer();
      if (l !== base()) {
        if (l.voi) setLayerVoi(l, l.voi);
        else shown.forEach((id) => viewport(id).resetProperties(l.volumeId));
        applyDisplay(l);
        return render();
      }
      all((vp) => {
        const invert = vp.getProperties(volumeId)?.invert;
        vp.resetProperties(volumeId);
        vp.setProperties({ invert }, volumeId);
      });
      applyDisplay(base());
    },
    toggleInvert() {
      all((vp) => vp.setProperties({ invert: !vp.getProperties(volumeId)?.invert }, volumeId));
    },
    resetView() {
      all((vp) => {
        vp.resetCamera();
        vp.resetProperties(volumeId);
      });
      applyDisplay(base());
      applyTool(activeTool); // re-centres the crosshairs on the reset cameras
    },
    async addLayer(overlay: LoadedSeries, display: LayerDisplay, options: LayerOptions = {}) {
      const uid = overlay.ref.seriesUid;
      const ids = registerSeriesMetadata(overlay);
      const overlayVolumeId = volumeIdFor(uid);
      const stopRefusal = onCacheRefusal(ids, () => options.onTooLarge?.());
      try {
        const v = (await volumeLoader.createAndCacheVolume(overlayVolumeId, { imageIds: ids })) as unknown as StreamingVolume;
        if (!v.loadStatus?.loaded) v.load();
        const layer: Layer = {
          seriesUid: uid,
          volumeId: overlayVolumeId,
          label: seriesLabel(overlay),
          modality: modalityOf(overlay),
          display: { ...display, curve: display.curve.map((p) => ({ ...p })) },
          suv: suvStatusOf(uid),
          voi: options.voi,
          styled: true,
          dispose: stopRefusal,
        };
        layers.push(layer);
        // Adding the actor fires VOI_MODIFIED while the other views don't have it yet; the VOI
        // synchronizer would then copy the overlay's window onto their base. Windows are set per view here.
        const baseVoi = layerVoi(base());
        sync?.setEnabled(false);
        try {
          // addVolumes hides the actor unless `visibility` is set (setVolumes doesn't).
          await addVolumesToViewports(engine, [{ volumeId: overlayVolumeId, visibility: true }], shown);
          applyDisplay(layer);
          if (layer.voi) setLayerVoi(layer, layer.voi);
          if (baseVoi) setLayerVoi(base(), baseVoi);
        } finally {
          sync?.setEnabled(true);
        }
        render();
      } catch (e) {
        stopRefusal();
        const i = layers.findIndex((l) => l.seriesUid === uid);
        if (i > 0) layers.splice(i, 1);
        throw e;
      }
    },
    removeLayer(uid: string) {
      const i = layers.findIndex((l) => l.seriesUid === uid);
      if (i < 1) return;
      const [layer] = layers.splice(i, 1);
      layer.dispose();
      shown.forEach((id) => viewport(id).removeVolumeActors([layer.volumeId]));
      if (selected === uid) {
        selected = base().seriesUid;
        applyTool(activeTool);
      }
      render();
    },
    setLayerDisplay(uid: string, change: Partial<LayerDisplay>) {
      const l = layerOf(uid);
      if (!l) return;
      l.display = { ...l.display, ...change, curve: (change.curve ?? l.display.curve).map((p) => ({ ...p })) };
      if (change.colormap) l.styled = true;
      applyDisplay(l);
      render();
    },
    selectLayer(uid: string) {
      if (!layerOf(uid) || uid === selected) return;
      selected = uid;
      applyTool(activeTool);
    },
    dispose() {
      stopStageListeners();
      layers.forEach((l) => l.dispose());
      teardown();
    },
  };
}
