// PROTOTYPE — throwaway. Ticket #214 (map #176): drawing annotations on WSI.
// One CS3D WHOLE_SLIDE viewport, two ways to draw on it:
//   cs3d — CS3D annotation tools in the tool group (what the #201 toolbar did)
//   dmv  — same viewport + CS3D pan/zoom, but the left button is handed to
//          dicom-microscopy-viewer's own Draw interaction (vp.viewer)
// Every drawn ROI is shown normalised to what TID 1500 needs (graphic type +
// slide-mm points). window.__spike is the hook for the Playwright driver.
import { Enums, RenderingEngine, init as csInit, utilities } from "@cornerstonejs/core";
import * as T from "@cornerstonejs/tools";
import dicomImageLoader from "@cornerstonejs/dicom-image-loader";
import { registerDefaultProviders, utilities as mdUtilities } from "@cornerstonejs/metadata";
import { api } from "dicomweb-client";

const WADO_ROOT = "https://d14fa38qiwhyfd.cloudfront.net/dicomweb";
const WSI = { study: "2.25.269859997690759739055099378767846712697", series: "2.25.274641717059635090989922952756233538416" };
const DMV_URL = new URL("dmv/", import.meta.url).href;

export type Variant = "cs3d" | "dmv";
// One tool model: toolbar names → CS3D tool or dmv geometry
export const WSI_DRAW_TOOLS: Record<string, { cs3d?: string; dmv?: { geometryType: string; maxPoints?: number; minPoints?: number } }> = {
  Point: { cs3d: T.ProbeTool.toolName, dmv: { geometryType: "point" } },
  Length: { cs3d: T.LengthTool.toolName, dmv: { geometryType: "line", maxPoints: 2, minPoints: 2 } },
  Polyline: { dmv: { geometryType: "line" } },
  Rectangle: { cs3d: T.RectangleROITool.toolName, dmv: { geometryType: "box" } },
  Ellipse: { cs3d: T.EllipticalROITool.toolName, dmv: { geometryType: "circle" } },
  Polygon: { dmv: { geometryType: "polygon" } },
  Freehand: { cs3d: T.PlanarFreehandROITool.toolName, dmv: { geometryType: "freehandpolygon" } },
};

async function peerImport(moduleId: string) {
  if (moduleId !== "dicom-microscopy-viewer") return undefined;
  const w = window as any;
  w.PUBLIC_URL = DMV_URL;
  w.PUBLIC_LIB_URL = "./";
  if (!w.dicomMicroscopyViewer) {
    await new Promise((res, rej) => {
      const s = document.createElement("script");
      s.src = `${DMV_URL}dicomMicroscopyViewer.min.js`;
      s.onload = res;
      s.onerror = rej;
      document.head.appendChild(s);
    });
  }
  return w.dicomMicroscopyViewer;
}

const TAG = (k: string) => mdUtilities.Tags.resolveHexFromKeyword(k)!;
const val = (inst: any, k: string) => inst[TAG(k)]?.Value?.[0];

export interface Roi { source: Variant; tool: string; graphicType: string; points: number[][]; measurements: Record<string, string> }

export async function startSpike(el: HTMLElement, variant: Variant, onChange: () => void) {
  registerDefaultProviders();
  dicomImageLoader.init();
  await csInit({ peerImport } as any);
  await T.init();
  [T.PanTool, T.ZoomTool, T.LengthTool, T.ProbeTool, T.RectangleROITool, T.EllipticalROITool, T.PlanarFreehandROITool].forEach((t) => T.addTool(t as any));

  const client: any = new api.DICOMwebClient({ url: WADO_ROOT } as any);
  const instances = await client.retrieveSeriesMetadata({ studyInstanceUID: WSI.study, seriesInstanceUID: WSI.series });
  const ids = instances.map((inst: any) => {
    const id = `wadors:${WADO_ROOT}/studies/${WSI.study}/series/${WSI.series}/instances/${val(inst, "SOPInstanceUID")}/frames/1`;
    dicomImageLoader.wadors.metaDataManager.add(id, inst);
    mdUtilities.addDicomWebInstance(id, inst);
    return id;
  });
  client.getDICOMwebMetadata = (id: string) => dicomImageLoader.wadors.metaDataManager.get(id);

  const engine = new RenderingEngine("spike");
  engine.enableElement({ viewportId: "wsi", type: Enums.ViewportType.WHOLE_SLIDE, element: el, defaultOptions: { background: [0.1, 0.1, 0.1] } } as any);
  const vp: any = engine.getViewport("wsi");
  const dataId = `wsi:${ids[0]}`;
  (utilities as any).genericViewportDisplaySetMetadataProvider.add(dataId, { imageIds: ids, options: { webClient: client } });
  await vp.setDisplaySets({ displaySetId: dataId });

  const tg = T.ToolGroupManager.createToolGroup("spike")!;
  for (const n of [T.PanTool, T.ZoomTool, T.LengthTool, T.ProbeTool, T.RectangleROITool, T.EllipticalROITool, T.PlanarFreehandROITool]) tg.addTool(n.toolName);
  tg.addViewport("wsi", "spike");
  const MB = T.Enums.MouseBindings;
  tg.setToolActive(T.PanTool.toolName, { bindings: [{ mouseButton: MB.Auxiliary }] });
  tg.setToolActive(T.ZoomTool.toolName, { bindings: [{ mouseButton: MB.Secondary }] });

  const dmvRois: Roi[] = [];
  const events: string[] = [];
  const log = (s: string) => { events.push(`${new Date().toISOString().slice(17, 23)} ${s}`); if (events.length > 30) events.shift(); };
  let tool = "";

  // dmv ROI → normalised form. scoord3d graphicData is already slide mm (x, y, z).
  const container = vp.viewer.getMap().getTargetElement() as HTMLElement;
  container.addEventListener("dicommicroscopyviewer_roi_drawn", (e: any) => {
    const roi = e.detail.payload ?? e.detail;
    const g = roi.scoord3d;
    const ms = (roi.measurements ?? []).map((m: any) => [m.ConceptNameCodeSequence?.[0]?.CodeMeaning ?? "?", `${(+m.MeasuredValueSequence?.[0]?.NumericValue).toFixed(3)} ${m.MeasuredValueSequence?.[0]?.MeasurementUnitsCodeSequence?.[0]?.CodeValue ?? ""}`]);
    dmvRois.push({ source: "dmv", tool, graphicType: g?.graphicType, points: (g?.graphicType === "POINT" ? [g.graphicData] : g?.graphicData ?? []).map((p: number[]) => p.map((x) => +x.toFixed(4))), measurements: Object.fromEntries(ms) });
    log(`dmv roi_drawn ${g?.graphicType}`);
    onChange();
  });
  const evt = T.Enums.Events;
  const { eventTarget } = await import("@cornerstonejs/core");
  eventTarget.addEventListener(evt.ANNOTATION_COMPLETED, (e: any) => { log(`cs3d completed ${e.detail.annotation.metadata.toolName}`); onChange(); });
  eventTarget.addEventListener(evt.ANNOTATION_ADDED, (e: any) => { log(`cs3d added ${e.detail.annotation.metadata.toolName}`); onChange(); });
  for (const t of ["mousedown", "pointerdown"]) el.addEventListener(t, (e: any) => log(`${t} btn=${e.button} target=${(e.target as HTMLElement).className || e.target.tagName}${e.defaultPrevented ? " (prevented)" : ""}`), true);

  const CS_GRAPHIC: Record<string, string> = { [T.ProbeTool.toolName]: "POINT", [T.LengthTool.toolName]: "POLYLINE", [T.RectangleROITool.toolName]: "POLYGON", [T.EllipticalROITool.toolName]: "ELLIPSE", [T.PlanarFreehandROITool.toolName]: "POLYGON" };
  const csRois = (): Roi[] => (T.annotation.state.getAllAnnotations() as any[]).map((a) => {
    const stats: any = Object.values(a.data.cachedStats ?? {})[0] ?? {};
    const ms = Object.entries(stats).filter(([, v]) => typeof v === "number").map(([k, v]) => [k, `${(v as number).toFixed(3)} ${stats[k + "Unit"] ?? stats.unit ?? ""}`]);
    const pts = (a.data.contour?.polyline?.length ? a.data.contour.polyline : a.data.handles.points) as number[][];
    return { source: "cs3d", tool: a.metadata.toolName, graphicType: CS_GRAPHIC[a.metadata.toolName] ?? "?", points: pts.map((p) => p.map((x) => +x.toFixed(4))), measurements: Object.fromEntries(ms) };
  });

  const api_ = {
    variant,
    vp,
    tg,
    T,
    get tool() { return tool; },
    events,
    setTool(name: string) {
      const def = WSI_DRAW_TOOLS[name];
      tool = name;
      for (const t of Object.values(WSI_DRAW_TOOLS)) if (t.cs3d) tg.setToolPassive(t.cs3d);
      vp.viewer.deactivateDrawInteraction();
      if (variant === "cs3d") {
        if (!def.cs3d) { log(`${name}: no CS3D tool`); tool = ""; }
        else tg.setToolActive(def.cs3d, { bindings: [{ mouseButton: MB.Primary }] });
      } else {
        vp.viewer.activateDrawInteraction({ ...def.dmv, bindings: { mouseButtons: ["left"] } });
      }
      log(`tool → ${name}`);
      onChange();
    },
    rois(): Roi[] { return variant === "cs3d" ? csRois() : dmvRois; },
    clear() { T.annotation.state.removeAllAnnotations(); vp.viewer.removeAllROIs?.(); dmvRois.length = 0; onChange(); },
    camera() { const c = vp.getCamera(); return { fp: c.focalPoint?.map((x: number) => +x.toFixed(3)), ps: +c.parallelScale.toFixed(3) }; },
  };
  (window as any).__spike = api_;
  return api_;
}

// Vite app build drops entry exports; the spike page reads this instead.
(window as any).wsiDrawSpike = { startSpike, WSI_DRAW_TOOLS };
