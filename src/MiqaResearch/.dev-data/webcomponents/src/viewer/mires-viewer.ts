// <mires-viewer>: the DICOM viewer element (spec #271). Lit in Shadow DOM.
// Talks to the rendering engine only through the ViewerAdapter seam (./adapter/adapter.ts);
// the Cornerstone3D adapter is imported lazily so unit tests never load CS3D.
//
// Chrome B (#280): series list | tool rail | viewport | inspector. Tools, presets, commands and
// inspector panels come from registries (tools/, commands.ts, inspector/) that later tickets
// extend from their own modules; see README.md "Extension points".
import { LitElement, css, html, nothing } from "lit";
import { customElement, property, state } from "lit/decorators.js";

import type { AdapterFactory, StackState, StackView, ViewerAdapter } from "./adapter/adapter.ts";
import { seriesList, seriesListItem, type SeriesListItem } from "./chrome/series-list.ts";
import { toolRail } from "./chrome/tool-rail.ts";
import { commands } from "./commands.ts";
import type { ViewerContext } from "./context.ts";
import { FirstRenderReport } from "./first-render.ts";
import { inspector } from "./inspector/index.ts";
import { burnedInWarning } from "./calibration.ts";
import { fetchSeries, type LoadedSeries } from "./series.ts";
import { presets, presetVoi, tools, voiToWindow, type Preset, type ViewportKind } from "./tools/index.ts";
import { unitTooltip } from "./units.ts";
import { isWholeSlide, WSI_DEFAULT_TOOL } from "./wsi.ts";

export type ViewerState = "loading" | "ready" | "error";

const DEFAULT_TOOL = "WindowLevel";

const cornerstoneAdapter: AdapterFactory = async () => {
  const { createCornerstoneAdapter } = await import("./adapter/cornerstone/index.ts");
  return createCornerstoneAdapter();
};

@customElement("mires-viewer")
export class MiresViewer extends LitElement {
  @property({ attribute: "wado-root" }) wadoRoot = "/api/v1/dicom";
  @property({ attribute: "study-uid" }) studyUid = "";
  @property({ attribute: "series-uid" }) seriesUid = "";
  /** Annotate role on this participant (set by the page from the server): Arrow, Calibrate, segment tools, Save. */
  @property({ type: Boolean, attribute: "can-annotate" }) canAnnotate = false;

  /** Reflected for pages and browser tests: loading → ready | error. */
  @property({ reflect: true }) state: ViewerState = "loading";

  /** Swapped by tests for a stub; defaults to the Cornerstone3D adapter. */
  adapterFactory: AdapterFactory = cornerstoneAdapter;

  @state() private stack: StackState | undefined;
  @state() private error = "";
  @state() private series: SeriesListItem[] = [];
  @state() private viewportKind: ViewportKind = "stack";

  private adapter: ViewerAdapter | undefined;
  private view: StackView | undefined;
  private loaded: LoadedSeries | undefined;
  private resizeObserver: ResizeObserver | undefined;
  private disposed = false;
  /** First-render marks + beacon (#293); volume views mark "interleaved" / "volume-loaded" on it. */
  firstRender: FirstRenderReport | undefined;

  static styles = css`
    :host { display: block; position: relative; background: #0b0d10; color: #d8dde3; font: 13px system-ui, sans-serif; outline: none; }
    .chrome { position: absolute; inset: 0; display: grid; grid-template-columns: 180px 56px minmax(0, 1fr) 250px; }
    button { font: inherit; color: inherit; background: #1b2027; border: 1px solid #2b323c; border-radius: 4px; padding: 4px 8px; cursor: pointer; }
    button:hover { background: #26303b; }
    button[aria-pressed="true"] { background: #1f6feb; border-color: #1f6feb; color: #fff; }
    button:disabled { opacity: 0.4; cursor: default; }
    kbd { font: 10px ui-monospace, monospace; background: #2b323c; border-radius: 3px; padding: 0 3px; color: #aab; }
    h5 { margin: 10px 0 6px; font-size: 10px; text-transform: uppercase; color: #6c7684; font-weight: 600; }
    .hint { color: #8a94a0; font-size: 12px; line-height: 1.5; }

    .series { background: #0f1318; border-right: 1px solid #262c35; overflow-y: auto; padding: 0 6px; }
    .ser { display: flex; gap: 6px; align-items: center; padding: 6px; border: 1px solid #262c35; border-radius: 4px; margin-bottom: 4px; background: #151a21; }
    .ser.shown { background: #16233a; }
    .ser .mod { font: 600 11px ui-monospace, monospace; background: #2b323c; border-radius: 3px; padding: 6px 4px; min-width: 22px; text-align: center; }
    .ser .txt { display: flex; flex-direction: column; min-width: 0; font-size: 12px; }
    .ser .txt b { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; font-weight: 500; }
    .ser .txt small { color: #7a8591; font-size: 10px; }

    .rail { background: #141920; border-right: 1px solid #262c35; display: flex; flex-direction: column; align-items: center; gap: 4px; padding: 4px 0; overflow-y: auto; }
    .rail h6 { margin: 8px 0 2px; font-size: 9px; text-transform: uppercase; color: #6c7684; font-weight: 600; }
    .rail button { width: 40px; height: 36px; font-size: 16px; padding: 0; position: relative; flex: none; }
    .rail button kbd { position: absolute; bottom: 1px; right: 2px; font-size: 8px; padding: 0 2px; }

    .stage { position: relative; background: #000; min-width: 0; min-height: 0; }
    .viewport { position: absolute; inset: 0; }
    .overlay { position: absolute; left: 8px; bottom: 8px; pointer-events: none; text-shadow: 0 0 2px #000; font: 12px ui-monospace, monospace; }
    .burned-in { position: absolute; left: 8px; top: 8px; z-index: 5; padding: 1px 6px; border-radius: 3px; font-size: 11px; cursor: help; background: #3b2a12; border: 1px solid #8a5a14; color: #ffcf7a; }
    .unit { position: absolute; right: 8px; top: 8px; z-index: 5; padding: 1px 6px; border-radius: 3px; font: 11px ui-monospace, monospace; cursor: help; background: #1d2b3b; border: 1px solid #2f4a6b; }
    [role="alert"] { position: absolute; inset: auto 8px 8px; color: #f88; }

    .inspector { background: #11151a; border-left: 1px solid #262c35; overflow-y: auto; padding: 0 10px 8px; }
    .inspector .grid2 { display: grid; grid-template-columns: 1fr 1fr; gap: 4px; }
    .inspector .grid2 button { text-align: left; font-size: 12px; }
    .inspector .row { display: flex; gap: 4px; margin-top: 6px; flex-wrap: wrap; }
    .inspector .badge { font: 11px ui-monospace, monospace; padding: 1px 6px; border-radius: 3px; background: #1d2b3b; border: 1px solid #2f4a6b; }
    .inspector .badge[data-level="warn"] { background: #3b2a12; border-color: #8a5a14; color: #ffcf7a; }
  `;

  /** Current stack state, for browser tests and diagnostics. */
  get stackState(): StackState | undefined {
    return this.view?.state();
  }

  /** The open stack view (scroll / window), for browser tests and diagnostics. */
  get stackView(): StackView | undefined {
    return this.view;
  }

  connectedCallback(): void {
    super.connectedCallback();
    this.disposed = false;
    if (!this.hasAttribute("tabindex")) this.tabIndex = 0;
    this.addEventListener("keydown", this.onKey);
  }

  disconnectedCallback(): void {
    super.disconnectedCallback();
    this.disposed = true;
    this.removeEventListener("keydown", this.onKey);
    this.resizeObserver?.disconnect();
    this.firstRender?.dispose();
    this.adapter?.destroy();
    this.adapter = undefined;
    this.view = undefined;
  }

  protected firstUpdated(): void {
    void this.open();
  }

  private async open(): Promise<void> {
    const viewport = this.renderRoot.querySelector<HTMLDivElement>(".viewport")!;
    this.firstRender = new FirstRenderReport();
    try {
      const series = await fetchSeries({ wadoRoot: this.wadoRoot, studyUid: this.studyUid, seriesUid: this.seriesUid });
      this.firstRender.series(series);
      this.series = [seriesListItem(series)];
      this.loaded = series;
      this.adapter = await this.adapterFactory();
      if (this.disposed) return this.adapter.destroy();
      const onChange = () => (this.stack = this.view?.state());
      const wsi = isWholeSlide(series);
      if (wsi) this.viewportKind = "wsi";
      this.view = await (wsi ? this.adapter.openWsi(viewport, series, onChange) : this.adapter.openStack(viewport, series, onChange));
      this.view.setTool(wsi ? WSI_DEFAULT_TOOL : DEFAULT_TOOL);
      this.stack = this.view.state();
      this.firstRender.mark("first-image");
      this.resizeObserver = new ResizeObserver(() => this.adapter?.resize());
      this.resizeObserver.observe(viewport);
      this.state = "ready";
    } catch (e) {
      this.error = e instanceof Error ? e.message : String(e);
      this.state = "error";
    }
  }

  /** What inspector panels and commands see; see context.ts. */
  private context(): ViewerContext {
    return {
      canAnnotate: this.canAnnotate,
      viewport: this.viewportKind,
      modality: this.series[0]?.modality ?? "",
      activeTool: this.stack?.activeTool ?? "",
      view: this.view,
      stack: this.stack,
      stackView: this.view,
      image: this.loaded?.images[this.stack?.imageIndex ?? 0]?.instance,
      selectTool: (id) => this.view?.setTool(id),
      applyPreset: (p) => this.applyPreset(p),
    };
  }

  private applyPreset(p: Preset): void {
    const voi = presetVoi(p);
    if (voi) this.view?.setVoi(voi);
    else this.view?.resetVoi();
  }

  private onKey = (e: KeyboardEvent): void => {
    if (!this.view || e.altKey || e.repeat) return;
    const target = e.composedPath()[0];
    if (target instanceof HTMLElement && target.matches("input, select, textarea, [contenteditable]")) return;
    const ctx = this.context();
    const mod = e.ctrlKey || e.metaKey;
    const command = commands.forKey(e.key, mod, ctx);
    if (command) {
      e.preventDefault();
      return command.run(ctx);
    }
    if (mod) return;
    const tool = tools.forKey(e.key, { viewport: ctx.viewport, canAnnotate: ctx.canAnnotate });
    if (tool) return ctx.selectTool(tool.id);
    const preset = presets.forKey(e.key, ctx.modality);
    if (preset) this.applyPreset(preset);
  };

  private overlay() {
    if (!this.stack || this.viewportKind === "wsi") return nothing;
    const { imageIndex, imageCount, voi } = this.stack;
    let window = "";
    if (voi) {
      const { width, center } = voiToWindow(voi);
      window = ` · W ${Math.round(width)} L ${Math.round(center)}`;
    }
    return html`<div class="overlay">Image ${imageIndex + 1} / ${imageCount}${window}</div>`;
  }

  private unit() {
    const unit = this.stack?.unit;
    if (!unit) return nothing;
    return html`<span class="unit" title=${unitTooltip(unit)}>${unit}</span>`;
  }

  /** Burned-in badge (#281): the image may carry identifying text in its pixels. */
  private burnedIn(ctx: ViewerContext) {
    if (!burnedInWarning(ctx.image)) return nothing;
    return html`<span class="burned-in" role="note" title="The image may have identifying text burned into its pixels (BurnedInAnnotation is YES, or missing on a secondary capture or ultrasound). Pixels aren't scrubbed.">⚠ Burned-in annotation</span>`;
  }

  render() {
    const ctx = this.context();
    const rail = tools.rail({ viewport: ctx.viewport, canAnnotate: ctx.canAnnotate });
    return html`<div class="chrome">
      ${seriesList(this.series)}
      ${toolRail(rail, ctx.activeTool, ctx.selectTool)}
      <div class="stage">
        <div class="viewport" tabindex="-1" @pointerdown=${() => this.focus()} @contextmenu=${(e: Event) => e.preventDefault()}></div>
        ${this.overlay()} ${this.unit()} ${this.burnedIn(ctx)}
        ${this.error ? html`<div role="alert">${this.error}</div>` : nothing}
      </div>
      <aside class="inspector" aria-label="Inspector">${inspector.panels().map((p) => p.render(ctx))}</aside>
    </div>`;
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "mires-viewer": MiresViewer;
  }
}
