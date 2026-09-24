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

async function imageIdsFor(client: any, study: string, series: string): Promise<string[]> {
  const instances = await client.retrieveSeriesMetadata({ studyInstanceUID: study, seriesInstanceUID: series });
  const ids = instances.map((inst: any) => {
    const id = `wadors:${WADO_ROOT}/studies/${study}/series/${series}/instances/${val(inst, "SOPInstanceUID")}/frames/1`;
    dicomImageLoader.wadors.metaDataManager.add(id, inst);
    mdUtilities.addDicomWebInstance(id, inst);
    return id;
  });
  if (val(instances[0], "Modality") === "PT") addSuvScaling(ids, instances);
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

export class Stage {
  engine!: RenderingEngine;
  mode: Mode;
  layout: Layout = "1x3";
  orientation: Orientation = "axial";
  role: Role;
  scheme: BindingScheme;
  simcal: SimCal;
  primary = "";
  fusionOpacity = 0.5;
  private tg!: csTools.Types.IToolGroup;
  private ctIds: string[] = [];
  private ptIds: string[] = [];
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

  tools(): ToolDef[] {
    return TOOLSETS[this.mode].map((k) => TOOLS[k]).filter((t) => !t.annotateOnly || this.role === "annotator");
  }
  presets() { return PRESETS[this.mode]; }
  viewportIds(): string[] {
    if (this.mode === "stack") return ["stack"];
    if (this.mode === "wsi") return ["wsi"];
    return this.layout === "1x1" ? ["ax"] : ["ax", "sag", "cor"];
  }

  async start(el: (id: string) => HTMLDivElement) {
    this.el = el;
    await initCornerstone();
    this.engine = new RenderingEngine("tb");
    if (this.mode === "wsi") await this.setupWsi();
    else {
      this.ctIds = await imageIdsFor(this.client, PETCT_STUDY, CT_SERIES);
      if (this.mode === "fusion") this.ptIds = await imageIdsFor(this.client, PETCT_STUDY, PT_SERIES);
      if (this.mode === "stack") await this.setupStack();
      else await this.setupVolumes();
    }
    eventTarget.addEventListener(T.Enums.Events.ANNOTATION_COMPLETED, this.onAnnotationCompleted as any);
    const ro = new ResizeObserver(() => this.engine.resize(true, true));
    ro.observe(el(this.viewportIds()[0]).parentElement!.parentElement!); // grid
    (window as any).__tb = this;
    (window as any).cornerstoneTools = csTools;
    this.onChange();
  }
  private el!: (id: string) => HTMLDivElement;

  private makeToolGroup() {
    T.ToolGroupManager.destroyToolGroup("tb");
    this.tg = T.ToolGroupManager.createToolGroup("tb")!;
    for (const t of this.tools()) {
      if (t.id === T.CrosshairsTool.toolName) {
        const colors: Record<string, string> = { ax: "rgb(220,50,50)", sag: "rgb(220,220,0)", cor: "rgb(50,200,50)" };
        this.tg.addTool(t.id, {
          getReferenceLineColor: (id: string) => colors[id],
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
      if (!isWsi) add(T.WindowLevelTool.toolName, { mouseButton: MB.Secondary });
      else add(T.ZoomTool.toolName, { mouseButton: MB.Secondary });
      add(T.PanTool.toolName, { mouseButton: MB.Auxiliary });
      if (!isWsi) {
        add(T.StackScrollTool.toolName, { mouseButton: MB.Wheel });
        add(T.ZoomTool.toolName, { mouseButton: MB.Wheel, modifierKey: KB.Ctrl });
      } else add(T.ZoomTool.toolName, { mouseButton: MB.Wheel });
    }
    for (const name of Object.keys(this.tg.getToolInstances())) {
      if (b[name]) this.tg.setToolActive(name, { bindings: b[name] });
      else if (this.isAnnotationTool(name) || (name === T.CrosshairsTool.toolName && this.viewportIds().length > 1)) this.tg.setToolPassive(name); // annotations stay editable, crosshair lines stay visible
      else this.tg.setToolDisabled(name);
    }
  }
  private isAnnotationTool(n: string) {
    return !["WindowLevel", "Pan", "Zoom", "StackScroll", "Crosshairs"].includes(n);
  }

  private async setupStack() {
    this.engine.enableElement({ viewportId: "stack", type: Enums.ViewportType.STACK, element: this.el("stack") });
    const vp = this.engine.getViewport("stack") as Types.IStackViewport;
    await vp.setStack(this.ctIds, Math.floor(this.ctIds.length / 2));
    this.makeToolGroup();
    this.tg.addViewport("stack", "tb");
    this.setPrimary(T.WindowLevelTool.toolName);
    vp.render();
  }

  private async setupVolumes() {
    const O = Enums.OrientationAxis;
    const orient: Record<string, any> = { ax: O.AXIAL, sag: O.SAGITTAL, cor: O.CORONAL };
    if (this.layout === "1x1") orient.ax = { axial: O.AXIAL, sagittal: O.SAGITTAL, coronal: O.CORONAL }[this.orientation];
    const ctVol = "cornerstoneStreamingImageVolume:CT";
    const ptVol = "cornerstoneStreamingImageVolume:PT";
    const ct = await volumeLoader.createAndCacheVolume(ctVol, { imageIds: this.ctIds });
    (ct as any).load();
    let pt: any;
    if (this.mode === "fusion") {
      pt = await volumeLoader.createAndCacheVolume(ptVol, { imageIds: this.ptIds });
      pt.load();
    }
    for (const id of this.viewportIds()) {
      this.engine.enableElement({
        viewportId: id,
        type: Enums.ViewportType.ORTHOGRAPHIC,
        element: this.el(id),
        defaultOptions: { orientation: orient[id], background: [0, 0, 0] as any },
      });
    }
    const inputs: any[] = [{ volumeId: ctVol }];
    if (pt) {
      inputs.push({
        volumeId: ptVol,
        callback: ({ volumeActor }: any) => {
          volumeActor.getProperty().getRGBTransferFunction(0).setMappingRange(0, 5);
        },
      });
    }
    await setVolumesForViewports(this.engine, inputs, this.viewportIds());
    if (pt) {
      for (const id of this.viewportIds()) {
        const vp = this.engine.getViewport(id) as Types.IVolumeViewport;
        vp.setProperties({ colormap: { name: "hsv", opacity: this.fusionOpacity } as any, voiRange: { lower: 0, upper: 5 } }, ptVol);
      }
    }
    this.makeToolGroup();
    this.viewportIds().forEach((id) => this.tg.addViewport(id, "tb"));
    this.setPrimary(this.layout === "1x3" ? T.CrosshairsTool.toolName : T.WindowLevelTool.toolName);
    this.engine.renderViewports(this.viewportIds());
  }

  private async setupWsi() {
    const ids = await imageIdsFor(this.client, WSI.study, WSI.series);
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
    if (this.mode !== "mpr" && this.mode !== "fusion") return;
    if (layout === this.layout) return;
    for (const id of this.viewportIds()) this.engine.disableElement(id);
    this.layout = layout;
    this.onChange(); // chrome re-renders the grid first
    await new Promise((r) => requestAnimationFrame(r));
    await this.setupVolumes();
    this.onChange();
  }

  async setOrientation(o: Orientation) {
    this.orientation = o;
    if (this.layout !== "1x1") return this.setLayout("1x1");
    const vp = this.engine.getViewport("ax") as Types.IVolumeViewport;
    vp.setOrientation({ axial: Enums.OrientationAxis.AXIAL, sagittal: Enums.OrientationAxis.SAGITTAL, coronal: Enums.OrientationAxis.CORONAL }[o]);
    vp.render();
    this.onChange();
  }

  applyPreset(p: Preset) {
    for (const id of this.viewportIds()) {
      const vp = this.engine.getViewport(id) as any;
      if (p.lower !== undefined) {
        vp.setProperties({ voiRange: { lower: p.lower, upper: p.upper } }, "cornerstoneStreamingImageVolume:PT");
      } else if (p.ww === undefined) {
        vp.resetProperties?.(this.mode === "fusion" ? "cornerstoneStreamingImageVolume:CT" : undefined);
      } else {
        const range = utilities.windowLevel.toLowHighRange(p.ww, p.wc!);
        vp.setProperties({ voiRange: range }, this.mode === "stack" ? undefined : "cornerstoneStreamingImageVolume:CT");
      }
      vp.render();
    }
    this.log(`preset: ${p.label}`);
    this.onChange();
  }

  setFusionOpacity(o: number) {
    this.fusionOpacity = o;
    for (const id of this.viewportIds()) {
      const vp = this.engine.getViewport(id) as any;
      vp.setProperties({ colormap: { name: "hsv", opacity: o } }, "cornerstoneStreamingImageVolume:PT");
      vp.render();
    }
    this.onChange();
  }

  invert() {
    for (const id of this.viewportIds()) {
      const vp = this.engine.getViewport(id) as any;
      if (this.mode === "wsi") continue;
      vp.setProperties({ invert: !vp.getProperties().invert });
      vp.render();
    }
  }

  reset() {
    for (const id of this.viewportIds()) {
      const vp = this.engine.getViewport(id) as any;
      vp.resetCamera?.();
      vp.resetProperties?.();
      vp.render();
    }
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

  info(): ViewportInfo[] {
    const labels: Record<string, string> = {
      stack: "CT · stack",
      ax: this.layout === "1x1" ? this.orientation : "axial",
      sag: "sagittal",
      cor: "coronal",
      wsi: "Slide · WSI",
    };
    return this.viewportIds().map((id) => {
      const vp = this.engine?.getViewport(id) as any;
      let voi = "";
      try {
        const r = vp?.getProperties?.(this.mode === "fusion" ? "cornerstoneStreamingImageVolume:CT" : undefined)?.voiRange;
        if (r) {
          const { windowWidth, windowCenter } = utilities.windowLevel.toWindowLevel(r.lower, r.upper);
          voi = `W ${Math.round(windowWidth)} L ${Math.round(windowCenter)}`;
        }
      } catch { /* not ready */ }
      const base = { id, label: labels[id], voi };
      if (this.mode === "wsi") return { ...base, badge: "mm", badgeLevel: "ok" as const, badgeLegend: "Slide coordinates from TotalPixelMatrix / ImagedVolume. Physical mm on the slide." };
      if (this.userCalibrated) return { ...base, ...SIMCAL.user };
      if (this.mode === "stack" && this.simcal) return { ...base, ...SIMCAL[this.simcal] };
      return { ...base, badge: "", badgeLevel: "none" as const, badgeLegend: "Tomographic mm (PixelSpacing) — trusted, badge hidden." };
    });
  }
}
