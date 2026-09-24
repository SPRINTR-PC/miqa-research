// PROTOTYPE — throwaway. Ticket #191 (map #176): can Cornerstone3D live in a
// Lit Shadow DOM, or must the viewer element render in light DOM?
// Variants (?variant=): shadow | light | shadow-mirrored (WSI/OpenLayers CSS
// copied from document.head into the shadow root).
// Data: public CS3D demo DICOMweb (our /frames endpoint 500s today, see #190).
import { LitElement, css, html } from "lit";
import { customElement, property } from "lit/decorators.js";
import {
  Enums,
  RenderingEngine,
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
  registerDefaultProviders,
  utilities as mdUtilities,
} from "@cornerstonejs/metadata";
import { api } from "dicomweb-client";

const WADO_ROOT = "https://d14fa38qiwhyfd.cloudfront.net/dicomweb";
const CT = {
  study: "1.3.6.1.4.1.14519.5.2.1.7009.2403.334240657131972136850343327463",
  series: "1.3.6.1.4.1.14519.5.2.1.7009.2403.226151125820845824875394858561",
};
const WSI = {
  study: "2.25.269859997690759739055099378767846712697",
  series: "2.25.274641717059635090989922952756233538416",
};
const DMV_URL = new URL("dmv/", import.meta.url).href;

const {
  ToolGroupManager,
  CrosshairsTool,
  PanTool,
  ZoomTool,
  StackScrollTool,
  LengthTool,
  WindowLevelTool,
  Enums: toolEnums,
} = csTools;
const { MouseBindings } = toolEnums;

let initPromise: Promise<void> | undefined;

async function peerImport(moduleId: string) {
  if (moduleId !== "dicom-microscopy-viewer") return undefined;
  const w = window as any;
  // dicom-microscopy-viewer resolves its data-loader worker from these globals.
  w.PUBLIC_URL = DMV_URL;
  w.PUBLIC_LIB_URL = "./";
  // UMD bundle: import() runs it as a module (this === undefined) and it throws,
  // so load it as a classic script that sets window.dicomMicroscopyViewer.
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
      utilities.calibratedPixelSpacingMetadataProvider.get.bind(
        utilities.calibratedPixelSpacingMetadataProvider,
      ),
      11000,
    );
    dicomImageLoader.init();
    volumeLoader.registerUnknownVolumeLoader(
      cornerstoneStreamingImageVolumeLoader as any,
    );
    volumeLoader.registerVolumeLoader(
      "cornerstoneStreamingImageVolume",
      cornerstoneStreamingImageVolumeLoader as any,
    );
    await csInit({ peerImport } as any);
    await csTools.init();
    [CrosshairsTool, PanTool, ZoomTool, StackScrollTool, LengthTool, WindowLevelTool].forEach(
      (t) => csTools.addTool(t),
    );
  })();
  return initPromise;
}

const TAG = (k: string) => mdUtilities.Tags.resolveHexFromKeyword(k)!;

async function imageIdsFor(
  client: any,
  study: string,
  series: string,
): Promise<string[]> {
  const instances = await client.retrieveSeriesMetadata({
    studyInstanceUID: study,
    seriesInstanceUID: series,
  });
  return instances.map((inst: any) => {
    const sop = inst[TAG("SOPInstanceUID")].Value[0];
    const id = `wadors:${WADO_ROOT}/studies/${study}/series/${series}/instances/${sop}/frames/1`;
    dicomImageLoader.wadors.metaDataManager.add(id, inst);
    mdUtilities.addDicomWebInstance(id, inst);
    return id;
  });
}

@customElement("mires-viewer-prototype")
export class MiresViewerPrototype extends LitElement {
  /** shadow | light | shadow-mirrored */
  @property() variant = "shadow";

  static styles = css`
    :host { display: block; font: 13px system-ui, sans-serif; }
    .row { display: flex; gap: 8px; margin: 8px 0 24px; flex-wrap: wrap; }
    .vp { width: 380px; height: 380px; background: #000; position: relative; }
    .wsi { width: 780px; height: 520px; background: #202; position: relative; }
    h3 { margin: 0; }
  `;

  // Light DOM variant: Lit renders into the element itself; static styles
  // are then not applied, so the page duplicates them (see index.html).
  createRenderRoot() {
    return this.variant === "light" ? this : super.createRenderRoot();
  }

  render() {
    return html`
      <h3>1. CT stack (StackViewport) — wheel: scroll, left: W/L, right: zoom, middle: pan, shift+left: length</h3>
      <div class="row"><div class="vp" id="stack" @contextmenu=${(e: Event) => e.preventDefault()}></div></div>
      <h3>2. Three views + crosshairs (ORTHOGRAPHIC volume viewports)</h3>
      <div class="row">
        <div class="vp" id="ax" @contextmenu=${(e: Event) => e.preventDefault()}></div>
        <div class="vp" id="sag" @contextmenu=${(e: Event) => e.preventDefault()}></div>
        <div class="vp" id="cor" @contextmenu=${(e: Event) => e.preventDefault()}></div>
      </div>
      <h3>3. WSI (WHOLE_SLIDE viewport, dicom-microscopy-viewer)</h3>
      <div class="row"><div class="wsi" id="wsi" @contextmenu=${(e: Event) => e.preventDefault()}></div></div>
    `;
  }

  private $(id: string) {
    return this.renderRoot.querySelector<HTMLDivElement>(`#${id}`)!;
  }

  private step(name: string, fn: () => Promise<void>) {
    const t0 = performance.now();
    return fn().then(
      () => report(name, "ok", `${Math.round(performance.now() - t0)} ms`),
      (e) => {
        console.error(name, e);
        report(name, "FAIL", String(e?.stack ?? e));
      },
    );
  }

  async firstUpdated() {
    report("render root", "info", this.renderRoot === this ? "light DOM" : "shadow root");
    await this.step("init", initCornerstone);
    const client = new api.DICOMwebClient({ url: WADO_ROOT } as any);
    const engine = new RenderingEngine("proto");
    let ctIds: string[] = [];
    await this.step("CT metadata", async () => {
      ctIds = await imageIdsFor(client, CT.study, CT.series);
    });
    await this.step("CT stack", () => this.stack(engine, ctIds));
    await this.step("three views + crosshairs", () => this.mpr(engine, ctIds));
    await this.step("WSI", () => this.wsi(engine, client));
    if (this.variant === "shadow-mirrored") this.mirrorHeadStyles();
    (window as any).__proto = { engine, el: this };
    (window as any).cornerstoneTools = csTools;
  }

  private async stack(engine: RenderingEngine, ids: string[]) {
    engine.enableElement({
      viewportId: "stack",
      type: Enums.ViewportType.STACK,
      element: this.$("stack"),
    });
    const vp = engine.getViewport("stack") as Types.IStackViewport;
    await vp.setStack(ids, Math.floor(ids.length / 2));
    const g = ToolGroupManager.createToolGroup("stackGroup")!;
    g.addTool(WindowLevelTool.toolName);
    g.addTool(PanTool.toolName);
    g.addTool(ZoomTool.toolName);
    g.addTool(StackScrollTool.toolName);
    g.addTool(LengthTool.toolName);
    g.setToolActive(WindowLevelTool.toolName, { bindings: [{ mouseButton: MouseBindings.Primary }] });
    g.setToolActive(LengthTool.toolName, {
      bindings: [{ mouseButton: MouseBindings.Primary, modifierKey: toolEnums.KeyboardBindings.Shift }],
    });
    g.setToolActive(PanTool.toolName, { bindings: [{ mouseButton: MouseBindings.Auxiliary }] });
    g.setToolActive(ZoomTool.toolName, { bindings: [{ mouseButton: MouseBindings.Secondary }] });
    g.setToolActive(StackScrollTool.toolName, { bindings: [{ mouseButton: MouseBindings.Wheel }] });
    g.addViewport("stack", "proto");
    vp.render();
  }

  private async mpr(engine: RenderingEngine, ids: string[]) {
    const volumeId = "cornerstoneStreamingImageVolume:CT";
    const volume = await volumeLoader.createAndCacheVolume(volumeId, { imageIds: ids });
    const O = Enums.OrientationAxis;
    const vps = [
      ["ax", O.AXIAL],
      ["sag", O.SAGITTAL],
      ["cor", O.CORONAL],
    ] as const;
    for (const [id, orientation] of vps) {
      engine.enableElement({
        viewportId: id,
        type: Enums.ViewportType.ORTHOGRAPHIC,
        element: this.$(id),
        defaultOptions: { orientation },
      });
    }
    (volume as any).load();
    await setVolumesForViewports(
      engine,
      [{ volumeId, callback: ({ volumeActor }: any) =>
          volumeActor.getProperty().getRGBTransferFunction(0)?.setMappingRange(-160, 240) }],
      vps.map(([id]) => id),
    );
    const g = ToolGroupManager.createToolGroup("mprGroup")!;
    vps.forEach(([id]) => g.addViewport(id, "proto"));
    g.addTool(PanTool.toolName);
    g.addTool(ZoomTool.toolName);
    g.addTool(StackScrollTool.toolName);
    const colors: Record<string, string> = { ax: "rgb(200,0,0)", sag: "rgb(200,200,0)", cor: "rgb(0,200,0)" };
    g.addTool(CrosshairsTool.toolName, {
      getReferenceLineColor: (id: string) => colors[id],
      getReferenceLineControllable: () => true,
      getReferenceLineDraggableRotatable: () => true,
      getReferenceLineSlabThicknessControlsOn: () => true,
    });
    g.setToolActive(CrosshairsTool.toolName, { bindings: [{ mouseButton: MouseBindings.Primary }] });
    g.setToolActive(PanTool.toolName, { bindings: [{ mouseButton: MouseBindings.Auxiliary }] });
    g.setToolActive(ZoomTool.toolName, { bindings: [{ mouseButton: MouseBindings.Secondary }] });
    g.setToolActive(StackScrollTool.toolName, { bindings: [{ mouseButton: MouseBindings.Wheel }] });
    engine.renderViewports(vps.map(([id]) => id));
  }

  private async wsi(engine: RenderingEngine, client: any) {
    const ids = await imageIdsFor(client, WSI.study, WSI.series);
    engine.enableElement({
      viewportId: "wsi",
      type: Enums.ViewportType.WHOLE_SLIDE,
      element: this.$("wsi"),
      defaultOptions: { background: [0.2, 0, 0.2] },
    } as any);
    const vp = engine.getViewport("wsi") as any;
    client.getDICOMwebMetadata = (id: string) => dicomImageLoader.wadors.metaDataManager.get(id);
    const dataId = `wsi:${ids[0]}`;
    (utilities as any).genericViewportDisplaySetMetadataProvider.add(dataId, {
      imageIds: ids,
      options: { webClient: client },
    });
    await vp.setDisplaySets({ displaySetId: dataId });
    const g = ToolGroupManager.createToolGroup("wsiGroup")!;
    g.addTool(PanTool.toolName);
    g.addTool(ZoomTool.toolName);
    g.addTool(LengthTool.toolName);
    g.setToolActive(PanTool.toolName, { bindings: [{ mouseButton: MouseBindings.Auxiliary }] });
    g.setToolActive(ZoomTool.toolName, { bindings: [{ mouseButton: MouseBindings.Secondary }] });
    g.setToolActive(LengthTool.toolName, { bindings: [{ mouseButton: MouseBindings.Primary }] });
    g.addViewport("wsi", "proto");
  }

  /** Copy <style> tags that libraries appended to document.head into the shadow root. */
  private mirrorHeadStyles() {
    const copied: string[] = [];
    document.head.querySelectorAll("style").forEach((s) => {
      if (s.hasAttribute("data-page")) return;
      this.renderRoot.appendChild(s.cloneNode(true));
      copied.push(s.id || `${s.textContent?.slice(0, 40)}…`);
    });
    report("mirrored head styles", "info", copied.join(" | ") || "none found");
  }
}

function report(name: string, status: string, detail = "") {
  window.dispatchEvent(new CustomEvent("proto-report", { detail: { name, status, detail } }));
}
