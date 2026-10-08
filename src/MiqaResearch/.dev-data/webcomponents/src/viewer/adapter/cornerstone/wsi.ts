// Whole-slide view (#285): CS3D WHOLE_SLIDE viewport (WSIViewport, beta) wrapping
// dicom-microscopy-viewer (dmv, OpenLayers). dmv is not bundled: it's served as-is from
// `dmv/` next to the viewer bundle (vite.viewer.config.ts copies dist/dynamic-import/) and
// loaded by `peerImport` with a classic <script>. Tools: the WSI set (Pan, Zoom, Length,
// ROIs, Arrow) on a tool group of its own; wheel = zoom (../../tools/bindings.ts).
import {
  Enums,
  eventTarget,
  registerViewportType,
  utilities as csUtils,
  WSIViewport,
  type RenderingEngine,
} from "@cornerstonejs/core";
import * as csTools from "@cornerstonejs/tools";
import { api } from "dicomweb-client";

import type { DicomJsonInstance, LoadedSeries } from "../../series.ts";
import { workstationBindings } from "../../tools/bindings.ts";
import { geometricTextLines, tilesCacheSize, wsiImageIds, type MeasurementStats } from "../../wsi.ts";
import type { StackState, StackView, VoiRange, WsiView } from "../adapter.ts";
import { bulkAnnotationLayer, type DmvAnnotationViewer } from "./bulk-annotations.ts";
import { registerSeriesMetadata } from "./metadata.ts";
import type { StackHandle } from "./stack.ts";
import { addToolsToGroup, applyBindingPlan } from "./tools.ts";

// ---- dicom-microscopy-viewer loading -------------------------------------------------------

/**
 * `<viewer bundle dir>/dmv/`. This module ends up in `chunks/` (the adapter is a dynamic
 * import), or in the entry next to `dmv/`; both resolve to the same directory.
 */
function dmvUrl(): string {
  // Via a variable: Vite rewrites a literal `new URL("…", import.meta.url)` as an asset import.
  const moduleUrl = import.meta.url;
  const here = new URL(".", moduleUrl).href;
  return new URL("dmv/", here.replace(/chunks\/$/, "")).href;
}

type DmvWindow = Window & { dicomMicroscopyViewer?: unknown; PUBLIC_URL?: string; PUBLIC_LIB_URL?: string };
let dmvPromise: Promise<unknown> | undefined;

/** CS3D `init({ peerImport })`: supplies dicom-microscopy-viewer to WSIViewport. */
export function peerImport(moduleId: string): Promise<unknown> {
  if (moduleId !== "dicom-microscopy-viewer") return Promise.resolve(null);
  const w = window as DmvWindow;
  // dmv resolves its data-loader worker and WASM codecs from these globals.
  w.PUBLIC_URL = dmvUrl();
  w.PUBLIC_LIB_URL = "./";
  // UMD bundle: as an ES module `this` is undefined and it throws, so load a classic script
  // that sets window.dicomMicroscopyViewer.
  dmvPromise ??= new Promise((resolve, reject) => {
    if (w.dicomMicroscopyViewer) return resolve(w.dicomMicroscopyViewer);
    const script = document.createElement("script");
    script.src = `${dmvUrl()}dicomMicroscopyViewer.min.js`;
    script.onload = () => resolve(w.dicomMicroscopyViewer);
    script.onerror = () => {
      dmvPromise = undefined;
      reject(new Error("dicom-microscopy-viewer failed to load"));
    };
    document.head.appendChild(script);
  });
  return dmvPromise;
}

// ---- WSIViewport subclass: dmv tile cache options ------------------------------------------

/** What `setWSI` touches of WSIViewport's private state (upstream WSIViewport.ts, 5.10.11). */
interface WsiInternals {
  microscopyElement: HTMLDivElement;
  imageIds: string[];
  imageURISet: Set<string>;
  frameOfReferenceUID: string | null;
  metadata: { hasPixelSpacing: boolean };
  hasPixelSpacing: boolean;
  viewer: unknown;
  map: { on(event: string, listener: () => void): void };
  postrender: () => void;
  resize(): void;
  clearDisplaySets(): void;
}

type DmvModule = {
  utils: unknown;
  viewer: { VolumeImageViewer: new (options: Record<string, unknown>) => DmvViewer };
};
type DmvViewer = {
  render(options: { container: HTMLElement }): void;
  deactivateDragPanInteraction(): void;
  getMap(): WsiInternals["map"];
};

/**
 * WSIViewport with dmv's tile cache options. Upstream constructs `VolumeImageViewer` with fixed
 * options (WSIViewport.ts `setWSI`), so dmv's default 1000-tile cache (~1 GiB at 512²) and no
 * preload apply. Same body as upstream 5.10.11 plus `tilesCacheSize` + `preload`.
 * TODO: drop when upstream exposes the viewer options (upstream PR, see #285).
 */
export class MiresWSIViewport extends WSIViewport {
  /** dmv tile cache, in tiles; set before setDataIds from the series' /metadata. */
  tilesCacheSize = 512;

  async setWSI(imageIds: string[], client: Parameters<WSIViewport["setWSI"]>[1]): Promise<void> {
    const self = this as unknown as WsiInternals;
    self.clearDisplaySets();
    self.microscopyElement.style.background = "black";
    self.microscopyElement.innerText = "Loading";
    self.imageIds = imageIds;
    const dmv = (await peerImport("dicom-microscopy-viewer")) as DmvModule;
    const loaded = await csUtils.WSIUtilities.loadWSIData({ imageIds, client, dicomMicroscopyViewer: dmv as never });
    self.imageURISet = loaded.imageURISet;
    self.frameOfReferenceUID = loaded.frameOfReferenceUID;
    self.metadata = loaded.metadata;
    self.hasPixelSpacing = loaded.metadata.hasPixelSpacing;
    const viewer = new dmv.viewer.VolumeImageViewer({
      client,
      metadata: loaded.volumeImages,
      controls: ["overview", "position"],
      retrieveRendered: false,
      bindings: {},
      tilesCacheSize: this.tilesCacheSize,
      preload: 1, // dmv: preload one coarser resolution level (any non-null value)
    });
    viewer.render({ container: self.microscopyElement });
    viewer.deactivateDragPanInteraction();
    self.viewer = viewer;
    self.map = viewer.getMap();
    self.map.on("postrender", self.postrender);
    self.resize();
    self.microscopyElement.innerText = "";
    Object.assign(self.microscopyElement.style, {
      "--ol-partial-background-color": "rgba(127, 127, 127, 0.7)",
      "--ol-foreground-color": "#000000",
      "--ol-subtle-foreground-color": "#000",
      "--ol-subtle-background-color": "rgba(78, 78, 78, 0.5)",
      background: "none",
    });
  }
}

let viewportTypeRegistered = false;

/** Make WHOLE_SLIDE viewports MiresWSIViewport (a resolver runs before the core type map). */
export function registerWsiViewport(): void {
  if (viewportTypeRegistered) return;
  viewportTypeRegistered = true;
  registerViewportType({
    type: "miresWholeSlide",
    ViewportClass: MiresWSIViewport as never,
    resolveClass: ({ type }: { type: string }) =>
      type === Enums.ViewportType.WHOLE_SLIDE ? (MiresWSIViewport as never) : undefined,
  } as never);
}

// ---- Shadow DOM: mirror head-injected CSS ---------------------------------------------------

/**
 * CS3D (`#wsiViewportOverlayCss`) and dmv/OpenLayers append <style> to document.head, which
 * doesn't reach into our shadow root: copy the ones that appeared while the slide opened.
 */
function mirrorHeadStyles(root: Node, before: Set<Element>): void {
  if (!(root instanceof ShadowRoot)) return;
  document.head.querySelectorAll("style").forEach((style) => {
    const known = style.id && root.getElementById(style.id);
    if (known || (before.has(style) && style.id !== "wsiViewportOverlayCss")) return;
    root.appendChild(style.cloneNode(true));
  });
}

// ---- The view --------------------------------------------------------------------------------

const ELEMENT_EVENTS = [Enums.Events.IMAGE_RENDERED, Enums.Events.CAMERA_MODIFIED];
const ANNOTATION_EVENTS = [csTools.Enums.Events.ANNOTATION_COMPLETED, csTools.Enums.Events.ANNOTATION_REMOVED];
/** WSI tools whose text box shows only geometric measurements (intensity stats are NaN here). */
const GEOMETRIC_TOOLS = [csTools.LengthTool, csTools.RectangleROITool, csTools.EllipticalROITool, csTools.PlanarFreehandROITool];

/** The OpenLayers View/Map members used here (dmv's map, through WSIViewport). */
type OlView = {
  getResolution(): number | undefined;
  getCenter(): number[] | undefined;
  getProjection(): { getExtent(): number[] };
  getResolutionForExtent(extent: number[], size: number[]): number;
  fit(extent: number[], options: { size: number[] }): void;
};
type OlMap = { getSize(): number[] | undefined };

export async function createWsiView(
  engine: RenderingEngine,
  element: HTMLDivElement,
  series: LoadedSeries,
  onChange: () => void,
): Promise<WsiView & Pick<StackHandle, "dispose">> {
  registerWsiViewport();
  const levels = wsiImageIds(series);
  const imageIds = registerSeriesMetadata({ ...series, images: levels });
  const instances = new Map<string, DicomJsonInstance>(levels.map((l) => [l.imageId, l.instance]));
  const client = new api.DICOMwebClient({
    // Absolute: dicomweb-client and dmv build URLs with `new URL(...)`, which rejects a bare path.
    url: new URL(series.ref.wadoRoot, document.baseURI).href.replace(/\/$/, ""),
    singlepart: false,
  });
  // WSIViewport reads each instance's DICOM JSON from the client; loadWSIData mutates it, so copy.
  Object.assign(client, {
    getDICOMwebMetadata: (imageId: string) => structuredClone(instances.get(imageId)),
  });

  const viewportId = `wsi-${engine.id}`;
  engine.enableElement({ viewportId, type: Enums.ViewportType.WHOLE_SLIDE, element });
  const viewport = engine.getViewport(viewportId) as unknown as MiresWSIViewport;
  // WSIViewport sets an inline `position: relative` on the element, which beats the element's
  // `position: absolute; inset: 0` and collapses it to 0 px high. Absolute is a containing block too.
  element.style.removeProperty("position");
  viewport.tilesCacheSize = tilesCacheSize(levels.map((l) => l.instance));

  const headStyles = new Set(document.head.querySelectorAll("style"));
  await viewport.setDataIds(imageIds, { webClient: client as never });
  mirrorHeadStyles(element.getRootNode(), headStyles);

  const toolGroupId = `tg-${viewportId}`;
  const toolGroup = csTools.ToolGroupManager.createToolGroup(toolGroupId)!;
  addToolsToGroup(toolGroup);
  const round = (n: number) => String(csUtils.roundNumber(n));
  for (const tool of GEOMETRIC_TOOLS) {
    toolGroup.setToolConfiguration(tool.toolName, {
      getTextLines: (data: { cachedStats?: Record<string, MeasurementStats> }, targetId: string) =>
        geometricTextLines(data.cachedStats?.[targetId], round),
    });
  }
  toolGroup.addViewport(viewportId, engine.id);
  let activeTool = "";
  const setTool = (toolId: string) => {
    applyBindingPlan(toolGroup, workstationBindings({ primary: toolId, viewport: "wsi" }));
    activeTool = toolId;
    onChange();
  };

  ELEMENT_EVENTS.forEach((e) => element.addEventListener(e, onChange));
  ANNOTATION_EVENTS.forEach((e) => eventTarget.addEventListener(e, onChange));

  const olView = () => viewport.getView() as unknown as OlView | undefined;
  const olSize = () => (viewport as unknown as { map?: OlMap }).map?.getSize();
  /** The whole slide fitted to the viewport: resolution and centre (zoom 1, pan 0). */
  const fit = (v: OlView) => {
    const [x0, y0, x1, y1] = v.getProjection().getExtent();
    const size = olSize();
    return {
      resolution: size ? v.getResolutionForExtent([x0, y0, x1, y1], size) : (v.getResolution() ?? 1),
      center: [(x0 + x1) / 2, (y0 + y1) / 2],
    };
  };
  const ownImages = new Set(imageIds);
  const frameOfReference = viewport.getFrameOfReferenceUID();
  const annotationCount = () =>
    csTools.annotation.state.getAllAnnotations().filter((a) => {
      const { referencedImageId, FrameOfReferenceUID } = a.metadata ?? {};
      return referencedImageId ? ownImages.has(referencedImageId) : FrameOfReferenceUID === frameOfReference;
    }).length;
  const unit = () => {
    const imageData = viewport.getImageData();
    return imageData ? csTools.utilities.getCalibratedLengthUnitsAndScale(imageData as never, []).unit : "";
  };
  let voi: VoiRange | undefined;

  const view: StackView = {
    state(): StackState {
      const v = olView();
      const home = v ? fit(v) : { resolution: 1, center: [0, 0] };
      const resolution = v?.getResolution() ?? home.resolution;
      const [cx, cy] = v?.getCenter() ?? home.center;
      return {
        imageIndex: 0,
        imageCount: 1,
        voi,
        activeTool,
        invert: false,
        // 1 = whole slide fitted to the viewport; pan in canvas pixels from the slide centre.
        zoom: home.resolution / resolution,
        pan: [(cx - home.center[0]) / resolution, (home.center[1] - cy) / resolution],
        unit: unit(),
        annotationCount: annotationCount(),
      };
    },
    scrollTo() {
      // One image: nothing to scroll.
    },
    setTool,
    setVoi(range: VoiRange) {
      voi = range;
      viewport.setProperties({ voiRange: range });
      onChange();
    },
    resetVoi() {
      voi = undefined;
      viewport.resetProperties();
      onChange();
    },
    toggleInvert() {
      // Not on WSI: dmv renders RGB tiles through OpenLayers, WSIViewport has no invert.
    },
    resetView() {
      const v = olView();
      const size = olSize();
      if (v && size) v.fit(v.getProjection().getExtent(), { size });
      voi = undefined;
      viewport.resetProperties();
      onChange();
    },
  };
  // Read-only bulk ANN (#292) on dmv's map.
  const bulk = bulkAnnotationLayer(() => (viewport as unknown as { viewer: DmvAnnotationViewer }).viewer, onChange);
  return {
    ...view,
    addBulkAnnotations: (instances) => bulk.add(instances),
    bulkAnnotationGroups: () => bulk.groups(),
    setBulkAnnotationGroupVisible: (uid, visible) => bulk.setVisible(uid, visible),
    dispose() {
      ELEMENT_EVENTS.forEach((e) => element.removeEventListener(e, onChange));
      ANNOTATION_EVENTS.forEach((e) => eventTarget.removeEventListener(e, onChange));
      csTools.ToolGroupManager.destroyToolGroup(toolGroupId);
    },
  };
}
