// PROTOTYPE — throwaway. Ticket #201 (map #176): viewer toolbar + interaction model.
// Shared CS3D "stage": loads demo data, sets up viewports per mode/layout and
// exposes a tiny tool API the three chrome variants drive. Chrome lives in
// mires-viewer-toolbar-prototype.ts; nothing here is UI.
import {
  Enums,
  RenderingEngine,
  eventTarget,
  init as csInit,
  metaData,
  setVolumesForViewports,
  utilities,
  volumeLoader,
  cornerstoneStreamingImageVolumeLoader,
  type Types,
} from "@cornerstonejs/core";
import * as csTools from "@cornerstonejs/tools";
import dicomImageLoader from "@cornerstonejs/dicom-image-loader";
import {
  calculateSUVScalingFactors,
  registerDefaultProviders,
  utilities as mdUtilities,
} from "@cornerstonejs/metadata";
import { api } from "dicomweb-client";

// Public CS3D demo DICOMweb (our /frames is not viewer-ready yet, see #190).
const WADO_ROOT = "https://d14fa38qiwhyfd.cloudfront.net/dicomweb";
const PETCT_STUDY = "1.3.6.1.4.1.14519.5.2.1.7009.2403.334240657131972136850343327463";
const CT_SERIES = "1.3.6.1.4.1.14519.5.2.1.7009.2403.226151125820845824875394858561";
const PT_SERIES = "1.3.6.1.4.1.14519.5.2.1.7009.2403.879445243400782656317561081015";
const WSI = {
  study: "2.25.269859997690759739055099378767846712697",
  series: "2.25.274641717059635090989922952756233538416",
};
const DMV_URL = new URL("dmv/", import.meta.url).href;

export type Mode = "stack" | "mpr" | "fusion" | "wsi";
export type Layout = "1x1" | "1x3";
export type Orientation = "axial" | "sagittal" | "coronal";
export type Role = "annotator" | "viewer";

const T = csTools;
class CalibrateTool extends T.LengthTool {
  static toolName = "Calibrate";
}

export interface ToolDef {
  id: string; // CS3D tool name
  label: string;
  key: string; // keyboard shortcut
  group: "navigate" | "measure" | "annotate" | "calibrate";
  icon: string;
  annotateOnly?: boolean;
}

const TOOLS: Record<string, ToolDef> = {
  WindowLevel: { id: T.WindowLevelTool.toolName, label: "Window/Level", key: "w", group: "navigate", icon: "◐" },
  Pan: { id: T.PanTool.toolName, label: "Pan", key: "p", group: "navigate", icon: "✥" },
  Zoom: { id: T.ZoomTool.toolName, label: "Zoom", key: "z", group: "navigate", icon: "⌕" },
  StackScroll: { id: T.StackScrollTool.toolName, label: "Scroll slices", key: "s", group: "navigate", icon: "⇕" },
  Crosshairs: { id: T.CrosshairsTool.toolName, label: "Crosshairs", key: "x", group: "navigate", icon: "✚" },
  Length: { id: T.LengthTool.toolName, label: "Length", key: "l", group: "measure", icon: "📏" },
  Angle: { id: T.AngleTool.toolName, label: "Angle", key: "a", group: "measure", icon: "∠" },
  Bidirectional: { id: T.BidirectionalTool.toolName, label: "Bidirectional", key: "b", group: "measure", icon: "✛" },
  Probe: { id: T.ProbeTool.toolName, label: "Probe (HU/SUV)", key: "o", group: "measure", icon: "⊙" },
  RectangleROI: { id: T.RectangleROITool.toolName, label: "Rectangle ROI", key: "r", group: "measure", icon: "▭" },
  EllipticalROI: { id: T.EllipticalROITool.toolName, label: "Ellipse ROI", key: "e", group: "measure", icon: "◯" },
  Freehand: { id: T.PlanarFreehandROITool.toolName, label: "Freehand ROI", key: "f", group: "measure", icon: "✎" },
  Arrow: { id: T.ArrowAnnotateTool.toolName, label: "Arrow + text", key: "t", group: "annotate", icon: "➚", annotateOnly: true },
  Calibrate: { id: CalibrateTool.toolName, label: "Calibrate (User)", key: "c", group: "calibrate", icon: "⟷", annotateOnly: true },
};

/** Proposed tool set per viewport type (the thing #201 decides). */
export const TOOLSETS: Record<Mode, string[]> = {
  stack: ["WindowLevel", "Pan", "Zoom", "StackScroll", "Length", "Angle", "Bidirectional", "Probe", "RectangleROI", "EllipticalROI", "Freehand", "Arrow", "Calibrate"],
  mpr: ["Crosshairs", "WindowLevel", "Pan", "Zoom", "StackScroll", "Length", "Angle", "Bidirectional", "Probe", "RectangleROI", "EllipticalROI", "Freehand", "Arrow"],
  fusion: ["Crosshairs", "WindowLevel", "Pan", "Zoom", "StackScroll", "Length", "Probe", "RectangleROI", "EllipticalROI", "Arrow"],
  wsi: ["Pan", "Zoom", "Length", "RectangleROI", "EllipticalROI", "Freehand", "Arrow"],
};

export interface Preset { id: string; label: string; key: string; ww?: number; wc?: number; lower?: number; upper?: number }
export const PRESETS: Record<Mode, Preset[]> = {
  stack: ctPresets(),
  mpr: ctPresets(),
  fusion: [
    ...ctPresets().slice(0, 3),
    { id: "suv5", label: "PET SUV 0–5", key: "7", lower: 0, upper: 5 },
    { id: "suv10", label: "PET SUV 0–10", key: "8", lower: 0, upper: 10 },
  ],
  wsi: [],
};
function ctPresets(): Preset[] {
  return [
    { id: "dicom", label: "DICOM default", key: "0" },
    { id: "soft", label: "Soft tissue", key: "1", ww: 400, wc: 40 },
    { id: "lung", label: "Lung", key: "2", ww: 1500, wc: -600 },
    { id: "bone", label: "Bone", key: "3", ww: 2500, wc: 480 },
    { id: "brain", label: "Brain", key: "4", ww: 80, wc: 40 },
    { id: "liver", label: "Liver", key: "5", ww: 150, wc: 90 },
    { id: "mediast", label: "Mediastinum", key: "6", ww: 350, wc: 50 },
  ];
}

/** Fixed secondary bindings; primary button = selected tool. */
export type BindingScheme = "ohif" | "workstation";
export const BINDINGS_HELP: Record<BindingScheme, string[]> = {
  ohif: ["Left: selected tool", "Middle drag: pan", "Right drag: zoom", "Wheel: scroll slices (WSI: zoom)", "Shift+Left: Length (quick measure)"],
  workstation: ["Left: selected tool", "Right drag: window/level", "Middle drag: pan", "Wheel: scroll slices", "Ctrl+Wheel: zoom (WSI: wheel = zoom)"],
};

let initPromise: Promise<void> | undefined;
async function peerImport(moduleId: string) {
  if (moduleId !== "dicom-microscopy-viewer") return undefined;
  const w = window as any;
  w.PUBLIC_URL = DMV_URL;
  w.PUBLIC_LIB_URL = "./";
  if (!w.dicomMicroscopyViewer) {
    await new Promise((resolve, reject) => {
      const s = document.createElement("script");
      s.src = `${DMV_URL}dicomMicroscopyViewer.min.js`;
      s.onload = resolve;
      s.onerror = reject;
      document.head.appendChild(s);
    });
  }
  return w.dicomMicroscopyViewer;
}

function initCornerstone() {
  initPromise ??= (async () => {
    registerDefaultProviders();
    metaData.addProvider(
      utilities.calibratedPixelSpacingMetadataProvider.get.bind(utilities.calibratedPixelSpacingMetadataProvider),
      11000,
    );
    dicomImageLoader.init();
    volumeLoader.registerUnknownVolumeLoader(cornerstoneStreamingImageVolumeLoader as any);
    volumeLoader.registerVolumeLoader("cornerstoneStreamingImageVolume", cornerstoneStreamingImageVolumeLoader as any);
    await csInit({ peerImport } as any);
    await T.init();
    [
      T.WindowLevelTool, T.PanTool, T.ZoomTool, T.StackScrollTool, T.CrosshairsTool, T.LengthTool,
      T.AngleTool, T.BidirectionalTool, T.ProbeTool, T.RectangleROITool, T.EllipticalROITool,
      T.PlanarFreehandROITool, T.ArrowAnnotateTool, CalibrateTool,
    ].forEach((t) => T.addTool(t as any));
  })();
  return initPromise;
}

const TAG = (k: string) => mdUtilities.Tags.resolveHexFromKeyword(k)!;
const val = (inst: any, k: string) => inst[TAG(k)]?.Value?.[0];

async function imageIdsFor(client: any, study: string, series: string, instances?: any[]): Promise<string[]> {
  instances ??= await client.retrieveSeriesMetadata({ studyInstanceUID: study, seriesInstanceUID: series });
  const ids = instances!.map((inst: any) => {
    const id = `wadors:${WADO_ROOT}/studies/${study}/series/${series}/instances/${val(inst, "SOPInstanceUID")}/frames/1`;
    dicomImageLoader.wadors.metaDataManager.add(id, inst);
    mdUtilities.addDicomWebInstance(id, inst);
    return id;
  });
  if (val(instances![0], "Modality") === "PT") addSuvScaling(ids, instances!);
  return ids;
}

/** SUVbw scaling module, as in the CS3D petCt example (#187). */
function addSuvScaling(ids: string[], instances: any[]) {
  const rp = val(instances[0], "RadiopharmaceuticalInformationSequence") ?? {};
  const meta = instances.map((i) => ({
    CorrectedImage: i[TAG("CorrectedImage")]?.Value,
    Units: val(i, "Units"),
    RadionuclideHalfLife: val(rp, "RadionuclideHalfLife"),
    RadionuclideTotalDose: val(rp, "RadionuclideTotalDose"),
    RadiopharmaceuticalStartTime: val(rp, "RadiopharmaceuticalStartTime"),
    RadiopharmaceuticalStartDateTime: val(rp, "RadiopharmaceuticalStartDateTime"),
    DecayCorrection: val(i, "DecayCorrection"),
    PatientWeight: val(i, "PatientWeight"),
    PatientSize: val(i, "PatientSize"),
    PatientSex: val(i, "PatientSex"),
    SeriesDate: val(i, "SeriesDate"),
    SeriesTime: val(i, "SeriesTime"),
    AcquisitionDate: val(i, "AcquisitionDate"),
    AcquisitionTime: val(i, "AcquisitionTime"),
    FrameReferenceTime: val(i, "FrameReferenceTime"),
    ActualFrameDuration: val(i, "ActualFrameDuration"),
  }));
  const factors = calculateSUVScalingFactors(meta as any);
  ids.forEach((id, n) => (utilities as any).genericMetadataProvider.add(id, { type: "scalingModule", metadata: factors[n] }));
}

export interface ViewportInfo {
  id: string;
  label: string;
  /** calibration badge text, or "" when hidden (tomographic mm) */
  badge: string;
  badgeLevel: "ok" | "warn" | "none";
  badgeLegend: string;
  voi: string;
}

/** Simulated calibration for the stack badge (demo CT is tomographic, badge would be hidden). */
export type SimCal = "" | "proj" | "ermf" | "none" | "user" | "us";
const SIMCAL: Record<Exclude<SimCal, "">, Omit<ViewportInfo, "id" | "label" | "voi">> = {
  proj: { badge: "mm Proj", badgeLevel: "warn", badgeLegend: "Projection X-ray, detector plane (ImagerPixelSpacing). Magnification not corrected: sizes at the patient are overestimated." },
  ermf: { badge: "mm ERMF", badgeLevel: "ok", badgeLegend: "Corrected with Estimated Radiographic Magnification Factor. Estimate, typically ±10%." },
  none: { badge: "px", badgeLevel: "warn", badgeLegend: "No pixel spacing in the image. Measurements are in pixels. Annotators can calibrate." },
  user: { badge: "mm User", badgeLevel: "warn", badgeLegend: "Calibrated by a user against a known length (stored with reference line in the SR)." },
  us: { badge: "cm US Region", badgeLevel: "ok", badgeLegend: "Ultrasound region calibration (SequenceOfUltrasoundRegions). Only valid inside the region." },
};

/** A series the viewer can show: the entry contract's "related series" list (#175). */
export interface SeriesItem {
  key: string;
  modality: string;
  description: string;
  count: number;
  frameOfReference: string;
  /** volumetric series can be shown in the three views / fused */
  volumetric: boolean;
}

/** One series shown in the three views; layers[0] is the base, the rest are overlays. */
export interface Layer {
  key: string;
  volumeId: string;
  colormap: string;
  lower?: number;
  upper?: number;
  opacity: number;
}

const VIEW_IDS = ["ax", "sag", "cor"] as const;
const ORIENT_COLOR: Record<Orientation, string> = { axial: "rgb(220,50,50)", sagittal: "rgb(220,220,0)", coronal: "rgb(50,200,50)" };
const ORIENT_AXIS = () => ({ axial: Enums.OrientationAxis.AXIAL, sagittal: Enums.OrientationAxis.SAGITTAL, coronal: Enums.OrientationAxis.CORONAL });
/** Curated vtk.js colormap presets (CS3D resolves names against vtkColorMaps; its own registry starts empty). */
export const COLORMAPS = ["Grayscale", "X Ray", "hsv", "jet", "Black-Body Radiation", "Inferno (matplotlib)", "Viridis (matplotlib)", "Plasma (matplotlib)", "Cool to Warm", "Rainbow Desaturated", "Reds", "Greens"];

export class Stage {
  engine!: RenderingEngine;
  mode: Mode;
  layout: Layout = "1x3";
  /** which orientation each volume viewport shows; "ax" is the big/main one */
  viewOrient: Record<string, Orientation> = { ax: "axial", sag: "sagittal", cor: "coronal" };
  role: Role;
  scheme: BindingScheme;
  simcal: SimCal;
  primary = "";
  catalog: SeriesItem[] = [];
  layers: Layer[] = [];
  /** layer index that presets and right-drag W/L act on */
  activeLayer = 0;
  private tg!: csTools.Types.IToolGroup;
  private ids: Record<string, string[]> = {};
  private client: any = new api.DICOMwebClient({ url: WADO_ROOT } as any);
  private userCalibrated = false;
  onChange: () => void = () => {};
  log: (s: string) => void = () => {};

  constructor(opts: { mode: Mode; role: Role; scheme: BindingScheme; simcal: SimCal }) {
    this.mode = opts.mode;
    this.role = opts.role;
    this.scheme = opts.scheme;
    this.simcal = opts.simcal;
    if (this.mode === "stack" || this.mode === "wsi") this.layout = "1x1";
  }

  get orientation(): Orientation { return this.viewOrient.ax; }

  tools(): ToolDef[] {
    return TOOLSETS[this.mode].map((k) => TOOLS[k]).filter((t) => !t.annotateOnly || this.role === "annotator");
  }
  presets() { return PRESETS[this.mode]; }
  isVolumeMode() { return this.mode === "mpr" || this.mode === "fusion"; }
  viewportIds(): string[] {
    if (this.mode === "stack") return ["stack"];
    if (this.mode === "wsi") return ["wsi"];
    return this.layout === "1x1" ? ["ax"] : [...VIEW_IDS];
  }
  series(key: string) { return this.catalog.find((c) => c.key === key)!; }

  async start(el: (id: string) => HTMLDivElement) {
    this.el = el;
    await initCornerstone();
    this.engine = new RenderingEngine("tb");
    await this.loadCatalog();
    if (this.mode === "wsi") await this.setupWsi();
    else if (this.mode === "stack") await this.setupStack();
    else {
      this.layers = [this.newLayer("CT", true)];
      if (this.mode === "fusion") this.layers.push(this.newLayer("PT", false));
      await this.setupVolumes();
    }
    eventTarget.addEventListener(T.Enums.Events.ANNOTATION_COMPLETED, this.onAnnotationCompleted as any);
    const ro = new ResizeObserver(() => this.engine.resize(true, true));
    ro.observe(el(this.viewportIds()[0]).parentElement!.parentElement!); // grid
    (window as any).__tb = this;
    (window as any).cornerstoneTools = csTools;
    this.onChange();
  }
  private el!: (id: string) => HTMLDivElement;

  /** Related series of the study. Demo: CT + PET (same FoR) and a WSI slide (other study). */
  private async loadCatalog() {
    const load = async (key: string, study: string, series: string) => {
      const instances = await this.client.retrieveSeriesMetadata({ studyInstanceUID: study, seriesInstanceUID: series });
      this.ids[key] = await imageIdsFor(this.client, study, series, instances);
      const i0 = instances[0];
      this.catalog.push({
        key,
        modality: val(i0, "Modality"),
        description: val(i0, "SeriesDescription") ?? "",
        count: instances.length,
        frameOfReference: val(i0, "FrameOfReferenceUID") ?? "",
        volumetric: val(i0, "Modality") !== "SM",
      });
    };
    await Promise.all([load("CT", PETCT_STUDY, CT_SERIES), load("PT", PETCT_STUDY, PT_SERIES), load("SM", WSI.study, WSI.series)]);
    this.catalog.sort((a, b) => ["CT", "PT", "SM"].indexOf(a.key) - ["CT", "PT", "SM"].indexOf(b.key));
  }

  private newLayer(key: string, base: boolean): Layer {
    const pt = this.series(key).modality === "PT";
    return {
      key,
      volumeId: `cornerstoneStreamingImageVolume:${key}`,
      colormap: base ? "Grayscale" : pt ? "hsv" : "Black-Body Radiation",
      ...(pt ? { lower: 0, upper: 5 } : {}),
      opacity: base ? 1 : 0.5,
    };
  }

  private makeToolGroup() {
    T.ToolGroupManager.destroyToolGroup("tb");
    this.tg = T.ToolGroupManager.createToolGroup("tb")!;
    for (const t of this.tools()) {
      if (t.id === T.CrosshairsTool.toolName) {
        this.tg.addTool(t.id, {
          getReferenceLineColor: (id: string) => ORIENT_COLOR[this.viewOrient[id]],
          getReferenceLineControllable: () => true,
          getReferenceLineDraggableRotatable: () => true,
          getReferenceLineSlabThicknessControlsOn: () => false,
        });
      } else this.tg.addTool(t.id);
    }
    // fixed secondary bindings (needs the navigate tools present even if hidden from the toolbar)
    for (const n of [T.PanTool.toolName, T.ZoomTool.toolName, T.StackScrollTool.toolName, T.WindowLevelTool.toolName, T.LengthTool.toolName]) {
      if (!this.tg.hasTool(n)) this.tg.addTool(n);
    }
  }

  private applyBindings() {
    const MB = T.Enums.MouseBindings;
    const KB = T.Enums.KeyboardBindings;
    const isWsi = this.mode === "wsi";
    const b: Record<string, any[]> = {};
    const add = (tool: string, binding: any) => (b[tool] ??= []).push(binding);
    add(this.primary, { mouseButton: MB.Primary });
    if (this.scheme === "ohif") {
      add(T.PanTool.toolName, { mouseButton: MB.Auxiliary });
      add(T.ZoomTool.toolName, { mouseButton: MB.Secondary });
      if (!isWsi) add(T.StackScrollTool.toolName, { mouseButton: MB.Wheel });
      else add(T.ZoomTool.toolName, { mouseButton: MB.Wheel });
      add(T.LengthTool.toolName, { mouseButton: MB.Primary, modifierKey: KB.Shift });
    } else {
      // right-drag W/L: CS3D's WindowLevelTool only windows the first volume of a
      // fused viewport, so overlay layers get the small handler in installLayerWL().
      if (!isWsi && this.activeLayer === 0) add(T.WindowLevelTool.toolName, { mouseButton: MB.Secondary });
      else if (isWsi) add(T.ZoomTool.toolName, { mouseButton: MB.Secondary });
      add(T.PanTool.toolName, { mouseButton: MB.Auxiliary });
      if (!isWsi) {
        add(T.StackScrollTool.toolName, { mouseButton: MB.Wheel });
        add(T.ZoomTool.toolName, { mouseButton: MB.Wheel, modifierKey: KB.Ctrl });
      } else add(T.ZoomTool.toolName, { mouseButton: MB.Wheel });
    }
    for (const name of Object.keys(this.tg.getToolInstances())) {
      // setToolActive merges into an already-active tool's bindings, so a former
      // primary tool would keep the left button: clear by disabling first.
      this.tg.setToolDisabled(name);
      if (b[name]) this.tg.setToolActive(name, { bindings: b[name] });
      else if (this.isAnnotationTool(name) || (name === T.CrosshairsTool.toolName && this.viewportIds().length > 1)) this.tg.setToolPassive(name); // annotations stay editable, crosshair lines stay visible
      else this.tg.setToolDisabled(name);
    }
  }
  private isAnnotationTool(n: string) {
    return !["WindowLevel", "Pan", "Zoom", "StackScroll", "Crosshairs"].includes(n);
  }

  /** Right-drag W/L for an overlay layer (active layer > 0), workstation scheme only. */
  private installLayerWL(el: HTMLElement) {
    if ((el as any).__layerWL) return;
    (el as any).__layerWL = true;
    let last: [number, number] | null = null;
    el.addEventListener("pointerdown", (e) => {
      if (e.button !== 2 || this.activeLayer === 0 || this.scheme !== "workstation") return;
      last = [e.clientX, e.clientY];
      e.stopPropagation();
    }, { capture: true });
    window.addEventListener("pointermove", (e) => {
      if (!last) return;
      const L = this.layers[this.activeLayer];
      if (!L) return;
      const { lower = 0, upper = 1 } = this.layerRange(this.activeLayer);
      let ww = upper - lower, wc = (upper + lower) / 2;
      const k = Math.max(ww, 1) / 300;
      ww = Math.max(k, ww + (e.clientX - last[0]) * k);
      wc = wc - (e.clientY - last[1]) * k;
      this.setLayerRange(this.activeLayer, wc - ww / 2, wc + ww / 2);
      last = [e.clientX, e.clientY];
    });
    window.addEventListener("pointerup", () => (last = null));
  }

  private async setupStack() {
    this.engine.enableElement({ viewportId: "stack", type: Enums.ViewportType.STACK, element: this.el("stack") });
    const vp = this.engine.getViewport("stack") as Types.IStackViewport;
    const ids = this.ids.CT;
    await vp.setStack(ids, Math.floor(ids.length / 2));
    this.makeToolGroup();
    this.tg.addViewport("stack", "tb");
    this.setPrimary(T.WindowLevelTool.toolName);
    vp.render();
  }

  private async setupVolumes() {
    const axis = ORIENT_AXIS();
    for (const id of this.viewportIds()) {
      this.engine.enableElement({
        viewportId: id,
        type: Enums.ViewportType.ORTHOGRAPHIC,
        element: this.el(id),
        defaultOptions: { orientation: axis[this.viewOrient[id]], background: [0, 0, 0] as any },
      });
      this.installLayerWL(this.el(id));
    }
    await this.applyLayers();
    this.makeToolGroup();
    this.viewportIds().forEach((id) => this.tg.addViewport(id, "tb"));
    this.setPrimary(this.layout === "1x3" ? T.CrosshairsTool.toolName : T.WindowLevelTool.toolName);
    this.engine.renderViewports(this.viewportIds());
  }

  /** (Re)mount all layers' volumes on every volume viewport, then apply per-layer display. */
  private async applyLayers() {
    for (const L of this.layers) {
      const vol: any = await volumeLoader.createAndCacheVolume(L.volumeId, { imageIds: this.ids[L.key] });
      vol.load();
    }
    await setVolumesForViewports(this.engine, this.layers.map((L) => ({ volumeId: L.volumeId })), this.viewportIds());
    this.layers.forEach((_, i) => this.applyLayerDisplay(i));
  }

  private applyLayerDisplay(i: number) {
    const L = this.layers[i];
    for (const id of this.viewportIds()) {
      const vp = this.engine.getViewport(id) as any;
      const props: any = { colormap: { name: L.colormap, opacity: i === 0 ? 1 : L.opacity } };
      if (L.lower !== undefined) props.voiRange = { lower: L.lower, upper: L.upper };
      vp.setProperties(props, L.volumeId);
      vp.render();
    }
  }

  /** Current VOI of a layer (from the viewport, so CS3D's own W/L drag is reflected). */
  layerRange(i: number): { lower?: number; upper?: number } {
    const L = this.layers[i];
    try {
      const r = (this.engine.getViewport(this.viewportIds()[0]) as any).getProperties(L.volumeId)?.voiRange;
      if (r) return r;
    } catch { /* not ready */ }
    return { lower: L.lower, upper: L.upper };
  }

  setLayerRange(i: number, lower: number, upper: number) {
    Object.assign(this.layers[i], { lower, upper });
    this.applyLayerDisplay(i);
    this.onChange();
  }
  setLayerColormap(i: number, name: string) {
    this.layers[i].colormap = name;
    this.applyLayerDisplay(i);
    this.onChange();
  }
  setLayerOpacity(i: number, o: number) {
    this.layers[i].opacity = o;
    this.applyLayerDisplay(i);
    this.onChange();
  }
  setActiveLayer(i: number) {
    this.activeLayer = i;
    this.applyBindings();
    this.onChange();
  }

  /** Why a series can't be fused onto the current base, or "" if it can. */
  fuseBlocker(key: string): string {
    const s = this.series(key);
    if (!this.isVolumeMode()) return "Fusion needs the three-view (volume) viewer";
    if (!s.volumetric) return "Not a volume (WSI opens in its own viewer)";
    if (this.layers.some((L) => L.key === key)) return "Already shown";
    const base = this.series(this.layers[0].key);
    if (s.frameOfReference !== base.frameOfReference) return "Different Frame of Reference";
    return "";
  }
  replaceBlocker(key: string): string {
    const s = this.series(key);
    if (!this.isVolumeMode()) return "Prototype: replace only in the three-view viewer";
    if (!s.volumetric) return "Not a volume (WSI opens in its own viewer)";
    if (this.layers.length === 1 && this.layers[0].key === key) return "Already shown";
    return "";
  }

  async fuse(key: string) {
    const why = this.fuseBlocker(key);
    if (why) return this.log(`can't fuse ${key}: ${why}`);
    this.layers.push(this.newLayer(key, false));
    await this.applyLayers();
    this.activeLayer = this.layers.length - 1;
    this.applyBindings();
    this.log(`fused ${key}`);
    this.onChange();
  }
  async replace(key: string) {
    const why = this.replaceBlocker(key);
    if (why) return this.log(`can't replace with ${key}: ${why}`);
    this.layers = [this.newLayer(key, true)];
    if (this.series(key).modality === "PT") Object.assign(this.layers[0], { colormap: "Grayscale", lower: 0, upper: 5 });
    await this.applyLayers();
    this.activeLayer = 0;
    this.applyBindings();
    this.log(`showing ${key}`);
    this.onChange();
  }
  async removeLayer(i: number) {
    if (i === 0) return;
    this.layers.splice(i, 1);
    await this.applyLayers();
    this.activeLayer = Math.min(this.activeLayer, this.layers.length - 1);
    this.applyBindings();
    this.onChange();
  }

  private async setupWsi() {
    const ids = this.ids.SM;
    this.engine.enableElement({
      viewportId: "wsi",
      type: Enums.ViewportType.WHOLE_SLIDE,
      element: this.el("wsi"),
      defaultOptions: { background: [0.1, 0.1, 0.1] },
    } as any);
    const vp = this.engine.getViewport("wsi") as any;
    this.client.getDICOMwebMetadata = (id: string) => dicomImageLoader.wadors.metaDataManager.get(id);
    const dataId = `wsi:${ids[0]}`;
    (utilities as any).genericViewportDisplaySetMetadataProvider.add(dataId, { imageIds: ids, options: { webClient: this.client } });
    await vp.setDisplaySets({ displaySetId: dataId });
    this.makeToolGroup();
    this.tg.addViewport("wsi", "tb");
    this.setPrimary(T.PanTool.toolName);
  }

  setPrimary(tool: string) {
    if (tool === T.CrosshairsTool.toolName && this.viewportIds().length < 2) {
      this.log("Crosshairs need the 1×3 layout");
      return;
    }
    this.primary = tool;
    this.applyBindings();
    this.onChange();
  }

  async setLayout(layout: Layout) {
    if (!this.isVolumeMode()) return;
    if (layout === this.layout) return;
    for (const id of this.viewportIds()) this.engine.disableElement(id);
    this.layout = layout;
    this.onChange(); // chrome re-renders the grid first
    await new Promise((r) => requestAnimationFrame(r));
    await this.setupVolumes();
    this.onChange();
  }

  /** 1×1 with the given orientation in the main viewport. */
  async setOrientation(o: Orientation) {
    this.swapOrient("ax", Object.keys(this.viewOrient).find((k) => this.viewOrient[k] === o)!);
    if (this.layout !== "1x1") return this.setLayout("1x1");
    this.reorient(["ax"]);
  }

  /** Double-click on a small view: swap its orientation into the main (big) view. */
  swapWithMain(id: string) {
    if (id === "ax" || this.layout !== "1x3") return;
    this.swapOrient("ax", id);
    this.reorient(["ax", id]);
    this.log(`main view: ${this.viewOrient.ax}`);
  }

  private swapOrient(a: string, b: string) {
    if (a === b) return;
    [this.viewOrient[a], this.viewOrient[b]] = [this.viewOrient[b], this.viewOrient[a]];
  }

  private reorient(ids: string[]) {
    const axis = ORIENT_AXIS();
    for (const id of ids) {
      const vp = this.engine.getViewport(id) as Types.IVolumeViewport;
      vp.setOrientation(axis[this.viewOrient[id]]);
      vp.resetCamera();
    }
    this.engine.renderViewports(this.viewportIds());
    this.onChange();
  }

  /** Apply a preset: in volume modes it targets the layer whose modality it fits (active layer first). */
  applyPreset(p: Preset) {
    if (this.isVolumeMode()) {
      const fits = (i: number) => (p.lower !== undefined) === (this.series(this.layers[i].key).modality === "PT");
      const i = fits(this.activeLayer) ? this.activeLayer : this.layers.findIndex((_, n) => fits(n));
      if (i < 0) return this.log(`preset ${p.label}: no matching layer`);
      if (p.lower !== undefined) this.setLayerRange(i, p.lower, p.upper!);
      else if (p.ww === undefined) {
        Object.assign(this.layers[i], { lower: undefined, upper: undefined });
        for (const id of this.viewportIds()) (this.engine.getViewport(id) as any).resetProperties?.(this.layers[i].volumeId);
        this.applyLayerDisplay(i);
      } else {
        const r = utilities.windowLevel.toLowHighRange(p.ww, p.wc!);
        this.setLayerRange(i, r.lower, r.upper);
      }
    } else {
      const vp = this.engine.getViewport(this.viewportIds()[0]) as any;
      if (p.ww === undefined) vp.resetProperties?.();
      else vp.setProperties({ voiRange: utilities.windowLevel.toLowHighRange(p.ww, p.wc!) });
      vp.render();
    }
    this.log(`preset: ${p.label}`);
    this.onChange();
  }

  /** Presets that fit a layer's modality. */
  presetsForLayer(i: number): Preset[] {
    const pt = this.series(this.layers[i].key).modality === "PT";
    const all = [...ctPresets(), ...PRESETS.fusion.filter((p) => p.lower !== undefined)];
    return all.filter((p) => (p.lower !== undefined) === pt || (pt && p.id === "dicom"));
  }

  invert() {
    if (this.mode === "wsi") return;
    for (const id of this.viewportIds()) {
      const vp = this.engine.getViewport(id) as any;
      const vol = this.isVolumeMode() ? this.layers[this.activeLayer].volumeId : undefined;
      vp.setProperties({ invert: !vp.getProperties(vol).invert }, vol);
      vp.render();
    }
  }

  reset() {
    for (const id of this.viewportIds()) {
      const vp = this.engine.getViewport(id) as any;
      vp.resetCamera?.();
      if (!this.isVolumeMode()) vp.resetProperties?.();
      vp.render();
    }
    if (this.isVolumeMode()) this.layers.forEach((_, i) => this.applyLayerDisplay(i));
    this.onChange();
  }

  private onAnnotationCompleted = (evt: CustomEvent) => {
    const a = evt.detail.annotation;
    if (a.metadata.toolName !== CalibrateTool.toolName) {
      this.log(`annotation: ${a.metadata.toolName}`);
      return;
    }
    const measured = a.data.cachedStats && Object.values<any>(a.data.cachedStats)[0]?.length;
    const answer = window.prompt(`Measured ${measured?.toFixed?.(2) ?? "?"} (current units). True length in mm?`);
    T.annotation.state.removeAnnotation(a.annotationUID);
    const trueMm = Number(answer);
    if (!answer || !measured || !(trueMm > 0)) return this.onChange();
    const imageId = a.metadata.referencedImageId;
    T.utilities.calibrateImageSpacing(imageId, this.engine, { type: Enums.CalibrationTypes.USER, scale: measured / trueMm } as any);
    this.userCalibrated = true;
    this.log(`User calibration: ${measured.toFixed(2)} → ${trueMm} mm`);
    this.setPrimary(T.LengthTool.toolName);
  };

  static fmtRange(modality: string, r: { lower?: number; upper?: number }) {
    if (r.lower === undefined || r.upper === undefined) return "";
    if (modality === "PT") return `SUV ${r.lower.toFixed(1)}–${r.upper.toFixed(1)}`;
    const { windowWidth, windowCenter } = utilities.windowLevel.toWindowLevel(r.lower, r.upper);
    return `W ${Math.round(windowWidth)} L ${Math.round(windowCenter)}`;
  }

  info(): ViewportInfo[] {
    return this.viewportIds().map((id) => {
      const vp = this.engine?.getViewport(id) as any;
      let voi = "";
      let label = id === "stack" ? "CT · stack" : id === "wsi" ? "Slide · WSI" : this.viewOrient[id];
      try {
        if (this.isVolumeMode() && this.layers.length) {
          voi = this.layers.map((L, i) => `${L.key} ${Stage.fmtRange(this.series(L.key).modality, this.layerRange(i))}`).join(" · ");
          label += ` · ${this.layers.map((L) => L.key).join("+")}`;
        } else if (vp?.getProperties?.()?.voiRange) voi = Stage.fmtRange("CT", vp.getProperties().voiRange);
      } catch { /* not ready */ }
      const base = { id, label, voi };
      if (this.mode === "wsi") return { ...base, badge: "mm", badgeLevel: "ok" as const, badgeLegend: "Slide coordinates from TotalPixelMatrix / ImagedVolume. Physical mm on the slide." };
      if (this.userCalibrated) return { ...base, ...SIMCAL.user };
      if (this.mode === "stack" && this.simcal) return { ...base, ...SIMCAL[this.simcal] };
      return { ...base, badge: "", badgeLevel: "none" as const, badgeLegend: "Tomographic mm (PixelSpacing) — trusted, badge hidden." };
    });
  }
}
