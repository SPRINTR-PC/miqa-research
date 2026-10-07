// <mires-viewer>: the DICOM viewer element (spec #271). Lit in Shadow DOM.
// Talks to the rendering engine only through the ViewerAdapter seam (./adapter/adapter.ts);
// the Cornerstone3D adapter is imported lazily so unit tests never load CS3D.
import { LitElement, css, html, nothing } from "lit";
import { customElement, property, state } from "lit/decorators.js";

import type { AdapterFactory, StackState, StackView, ViewerAdapter } from "./adapter/adapter.ts";
import { fetchSeries } from "./series.ts";

export type ViewerState = "loading" | "ready" | "error";

const cornerstoneAdapter: AdapterFactory = async () => {
  const { createCornerstoneAdapter } = await import("./adapter/cornerstone/index.ts");
  return createCornerstoneAdapter();
};

@customElement("mires-viewer")
export class MiresViewer extends LitElement {
  @property({ attribute: "wado-root" }) wadoRoot = "/api/v1/dicom";
  @property({ attribute: "study-uid" }) studyUid = "";
  @property({ attribute: "series-uid" }) seriesUid = "";

  /** Reflected for pages and browser tests: loading → ready | error. */
  @property({ reflect: true }) state: ViewerState = "loading";

  /** Swapped by tests for a stub; defaults to the Cornerstone3D adapter. */
  adapterFactory: AdapterFactory = cornerstoneAdapter;

  @state() private stack: StackState | undefined;
  @state() private error = "";

  private adapter: ViewerAdapter | undefined;
  private view: StackView | undefined;
  private resizeObserver: ResizeObserver | undefined;
  private disposed = false;

  static styles = css`
    :host { display: block; position: relative; background: #000; color: #ddd; font: 13px system-ui, sans-serif; }
    .viewport { position: absolute; inset: 0; }
    .overlay { position: absolute; left: 8px; bottom: 8px; pointer-events: none; text-shadow: 0 0 2px #000; }
    [role="alert"] { position: absolute; inset: auto 8px 8px; color: #f88; }
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
  }

  disconnectedCallback(): void {
    super.disconnectedCallback();
    this.disposed = true;
    this.resizeObserver?.disconnect();
    this.adapter?.destroy();
    this.adapter = undefined;
    this.view = undefined;
  }

  protected firstUpdated(): void {
    void this.open();
  }

  private async open(): Promise<void> {
    const viewport = this.renderRoot.querySelector<HTMLDivElement>(".viewport")!;
    try {
      const series = await fetchSeries({ wadoRoot: this.wadoRoot, studyUid: this.studyUid, seriesUid: this.seriesUid });
      this.adapter = await this.adapterFactory();
      if (this.disposed) return this.adapter.destroy();
      this.view = await this.adapter.openStack(viewport, series, () => (this.stack = this.view?.state()));
      this.stack = this.view.state();
      this.resizeObserver = new ResizeObserver(() => this.adapter?.resize());
      this.resizeObserver.observe(viewport);
      this.state = "ready";
    } catch (e) {
      this.error = e instanceof Error ? e.message : String(e);
      this.state = "error";
    }
  }

  private overlay() {
    if (!this.stack) return nothing;
    const { imageIndex, imageCount, voi } = this.stack;
    // Linear VOI range → window width/centre (DICOM PS3.3 C.11.2.1.2, as CS3D's toWindowLevel).
    const window = voi
      ? ` · W ${Math.round(voi.upper - voi.lower + 1)} L ${Math.round((voi.upper + voi.lower + 1) / 2)}`
      : "";
    return html`<div class="overlay">Image ${imageIndex + 1} / ${imageCount}${window}</div>`;
  }

  render() {
    return html`
      <div class="viewport" tabindex="0" @contextmenu=${(e: Event) => e.preventDefault()}></div>
      ${this.overlay()}
      ${this.error ? html`<div role="alert">${this.error}</div>` : nothing}
    `;
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "mires-viewer": MiresViewer;
  }
}
