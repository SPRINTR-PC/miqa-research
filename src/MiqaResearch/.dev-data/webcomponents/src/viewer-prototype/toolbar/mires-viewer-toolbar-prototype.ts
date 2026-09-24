// PROTOTYPE — throwaway. Ticket #201 (map #176): three structurally different
// toolbar / interaction models over the same CS3D stage, switchable via ?variant=.
//   A — Top toolbar (OHIF-style): grouped horizontal bar, dropdowns, OHIF mouse bindings.
//   B — Left tool rail + right inspector: tools by group, settings/legend in a side panel,
//       workstation bindings (right-drag = W/L).
//   C — Chromeless, keyboard-first: full-bleed viewports, per-viewport hover HUD,
//       Space = command palette, ? = shortcut sheet.
// Shadow DOM kept (#191): head-injected WSI CSS is mirrored into the shadow root.
import { LitElement, css, html, nothing } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import { BINDINGS_HELP, Stage, COLORMAPS, type Mode, type Preset, type Role, type SimCal, type ToolDef, type ViewportInfo } from "./stage.js";

@customElement("mires-viewer-toolbar-prototype")
export class MiresViewerToolbarPrototype extends LitElement {
  @property() variant: "A" | "B" | "C" = "A";
  @property() mode: Mode = "mpr";
  @property() role: Role = "annotator";
  @property() simcal: SimCal = "";
  @state() private tick = 0;
  @state() private status = "loading…";
  @state() private open = ""; // open dropdown / overlay id
  @state() private paletteQuery = "";
  stage!: Stage;

  static styles = css`
    :host { display: flex; flex-direction: column; height: 100%; background: #0b0d10; color: #d8dde3; font: 13px system-ui, sans-serif; outline: none; }
    button { font: inherit; color: inherit; background: #1b2027; border: 1px solid #2b323c; border-radius: 4px; padding: 4px 8px; cursor: pointer; }
    button:hover { background: #26303b; }
    button.on { background: #1f6feb; border-color: #1f6feb; color: #fff; }
    button:disabled { opacity: .35; cursor: default; }
    kbd { font: 11px ui-monospace, monospace; background: #2b323c; border-radius: 3px; padding: 0 4px; color: #aab; }
    .main { flex: 1; display: flex; min-height: 0; }
    .grid { flex: 1; display: grid; gap: 2px; background: #222; min-width: 0; }
    .grid.n1 { grid-template-columns: 1fr; }
    .grid.n3 { grid-template-columns: 1fr 1fr 1fr; }
    .grid.b3 { grid-template-columns: var(--split) 6px 1fr; grid-template-rows: 1fr 1fr; gap: 0; }
    .grid.b3 .c-ax { grid-area: 1 / 1 / 3 / 2; }
    .grid.b3 .divider { grid-area: 1 / 2 / 3 / 3; background: #262c35; cursor: col-resize; touch-action: none; }
    .grid.b3 .divider:hover { background: #1f6feb; }
    .grid.b3 .c-sag { grid-area: 1 / 3 / 2 / 4; border-bottom: 2px solid #222; }
    .grid.b3 .c-cor { grid-area: 2 / 3 / 3 / 4; }
    .cell { position: relative; background: #000; min-width: 0; min-height: 0; }
    .vp { position: absolute; inset: 0; width: 100%; height: 100%; }
    .ov { position: absolute; font: 12px ui-monospace, monospace; color: #cfd6de; pointer-events: none; text-shadow: 0 0 3px #000; z-index: 5; }
    .tl { top: 6px; left: 8px; } .bl { bottom: 6px; left: 8px; } .tr { top: 6px; right: 8px; pointer-events: auto; } .wsi-cell .tr { top: 34px; }
    .badge { display: inline-block; padding: 1px 6px; border-radius: 3px; font: 11px ui-monospace, monospace; cursor: help; }
    .badge.ok { background: #1d3b2a; color: #7ee2a8; border: 1px solid #2f6b47; }
    .badge.warn { background: #4a3510; color: #ffcc66; border: 1px solid #8a6420; }
    .legend { position: absolute; right: 0; top: 22px; width: 260px; background: #11151a; border: 1px solid #333; padding: 8px; border-radius: 4px; font: 12px system-ui; white-space: normal; color: #ccd; display: none; }
    .tr:hover .legend { display: block; }
    .status { font: 11px ui-monospace, monospace; color: #7a8591; padding: 2px 8px; border-top: 1px solid #1c2128; }

    /* A — top toolbar */
    .A-bar { display: flex; gap: 12px; align-items: center; padding: 6px 8px; background: #141920; border-bottom: 1px solid #262c35; flex-wrap: wrap; }
    .A-grp { display: flex; gap: 2px; align-items: center; }
    .A-grp > label { font-size: 10px; text-transform: uppercase; color: #6c7684; margin-right: 4px; }
    .dd { position: relative; }
    .dd-menu { position: absolute; top: 100%; left: 0; z-index: 20; background: #141920; border: 1px solid #333; border-radius: 4px; min-width: 190px; padding: 4px; display: flex; flex-direction: column; gap: 2px; }
    .dd-menu button { text-align: left; border: 0; display: flex; justify-content: space-between; gap: 12px; }

    /* B — rail + inspector */
    .B-rail { width: 56px; background: #141920; border-right: 1px solid #262c35; display: flex; flex-direction: column; align-items: center; gap: 4px; padding: 6px 0; overflow-y: auto; }
    .B-rail h6 { margin: 8px 0 2px; font-size: 9px; text-transform: uppercase; color: #6c7684; font-weight: 600; }
    .B-rail button { width: 40px; height: 36px; font-size: 16px; padding: 0; position: relative; }
    .B-rail button kbd { position: absolute; bottom: 1px; right: 2px; font-size: 8px; padding: 0 2px; }
    .B-insp { width: 260px; background: #11151a; border-left: 1px solid #262c35; overflow-y: auto; padding: 8px 10px; }
    .B-insp h5 { margin: 12px 0 6px; font-size: 10px; text-transform: uppercase; color: #6c7684; }
    .B-layouts { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; }
    .B-layouts button { height: 48px; display: flex; flex-direction: column; justify-content: center; align-items: center; font-size: 11px; }
    .B-presets { display: grid; grid-template-columns: 1fr 1fr; gap: 4px; }
    .B-presets button { font-size: 12px; text-align: left; }
    .B-cal { font-size: 12px; margin: 4px 0; line-height: 1.4; }

    .B-series { width: 190px; background: #0f1318; border-right: 1px solid #262c35; overflow-y: auto; padding: 6px; }
    .B-series h5, .B-insp h5 { margin: 8px 0 6px; font-size: 10px; text-transform: uppercase; color: #6c7684; }
    .ser { display: flex; gap: 6px; align-items: center; padding: 6px; border: 1px solid #262c35; border-radius: 4px; margin-bottom: 4px; cursor: grab; background: #151a21; }
    .ser:hover { border-color: #1f6feb; } .ser.shown { background: #16233a; }
    .ser-mod { font: 600 11px ui-monospace, monospace; background: #2b323c; border-radius: 3px; padding: 6px 4px; min-width: 22px; text-align: center; }
    .ser-txt { display: flex; flex-direction: column; min-width: 0; font-size: 12px; } .ser-txt span { color: #7a8591; font-size: 10px; }
    .ser-txt b { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; font-weight: 500; }
    .chip { margin-left: auto; font-size: 9px; text-transform: uppercase; background: #2b323c; border-radius: 3px; padding: 1px 4px; color: #aab; }
    .chip.ov2 { background: #5a3d0a; color: #ffcc66; }
    .hint { color: #6c7684; font-size: 11px; }
    .dz { position: absolute; inset: 0; z-index: 25; display: grid; grid-template-rows: 1fr 1fr; gap: 4px; padding: 4px; background: #0008; }
    .dz-half { border: 2px dashed #5b6b80; border-radius: 8px; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 4px; color: #dde; font-size: 16px; }
    .dz-half small { font-size: 12px; color: #9aa6b4; }
    .dz-half.hot { border-color: #1f6feb; background: #1f6feb33; }
    .dz-half.no { border-color: #6b2f2f; color: #a77; background: #2a0f0f55; }
    .layer { border: 1px solid #262c35; border-radius: 4px; padding: 6px; margin-bottom: 6px; cursor: pointer; }
    .layer.act { border-color: #1f6feb; background: #1f6feb14; }
    .lh { display: flex; justify-content: space-between; align-items: center; gap: 6px; font-size: 12px; margin-bottom: 4px; }
    .lh span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .lr { margin: 4px 0; font-size: 12px; } .lr select { width: 100%; background: #1b2027; color: inherit; border: 1px solid #2b323c; border-radius: 4px; padding: 3px; }
    .lr.nums { display: flex; gap: 6px; } .lr.nums label { display: flex; gap: 4px; align-items: center; flex: 1; }
    .lr.nums input { width: 100%; min-width: 0; background: #0b0d10; color: inherit; border: 1px solid #2b323c; border-radius: 3px; padding: 2px 4px; }
    .lr input[type=range] { width: 140px; vertical-align: middle; }
    button.x { padding: 0 6px; }

    /* C — chromeless */
    .C-hud { position: absolute; top: 0; left: 0; right: 0; display: flex; gap: 4px; justify-content: center; padding: 6px; opacity: 0; transition: opacity .15s; z-index: 6; }
    .cell:hover .C-hud { opacity: 1; }
    .C-hud button { background: #000a; font-size: 11px; padding: 2px 6px; }
    .C-pill { position: absolute; bottom: 14px; left: 14px; z-index: 30; background: #141920ee; border: 1px solid #333; border-radius: 999px; padding: 4px 12px; display: flex; gap: 10px; align-items: center; }
    .C-overlay { position: absolute; inset: 0; background: #000b; z-index: 40; display: flex; align-items: flex-start; justify-content: center; padding-top: 10vh; }
    .C-box { background: #141920; border: 1px solid #333; border-radius: 8px; width: 520px; max-height: 70vh; overflow: auto; padding: 10px; }
    .C-box input { width: 100%; box-sizing: border-box; font: 15px system-ui; padding: 8px; background: #0b0d10; color: #fff; border: 1px solid #333; border-radius: 4px; }
    .C-box .row { display: flex; justify-content: space-between; padding: 5px 8px; border-radius: 4px; cursor: pointer; }
    .C-box .row:hover, .C-box .row.sel { background: #1f6feb44; }
    .C-sheet { columns: 2; font-size: 12px; } .C-sheet div { display: flex; justify-content: space-between; padding: 2px 6px; break-inside: avoid; }
  `;

  constructor() {
    super();
    this.addEventListener("keydown", (e) => this.onKey(e));
  }

  connectedCallback() {
    super.connectedCallback();
    this.tabIndex = 0;
  }

  async firstUpdated() {
    this.stage = new Stage({ mode: this.mode, role: this.role, scheme: this.variant === "B" ? "workstation" : "ohif", simcal: this.simcal });
    this.stage.onChange = () => this.tick++;
    this.stage.log = (s) => (this.status = s);
    try {
      await this.stage.start((id) => this.renderRoot.querySelector<HTMLDivElement>(`#${id}`)!);
      this.status = "ready";
    } catch (e: any) {
      this.status = `FAIL ${e?.message ?? e}`;
      console.error(e);
    }
    if (this.mode === "wsi") this.mirrorHeadStyles();
    this.focus();
  }

  /** #191: WSI overview/position CSS is injected into document.head; copy it into the shadow root. */
  private mirrorHeadStyles() {
    document.head.querySelectorAll("style").forEach((s) => {
      if (!s.hasAttribute("data-page")) this.renderRoot.appendChild(s.cloneNode(true));
    });
  }

  // ---------- shared bits ----------
  private get s() { return this.stage; }
  private ready() { return !!this.s?.engine; }
  private tools(): ToolDef[] { return this.ready() ? this.s.tools() : []; }
  private presets(): Preset[] { return this.ready() ? this.s.presets() : []; }
  private isVol() { return this.mode === "mpr" || this.mode === "fusion"; }

  private grid(hud?: (v: ViewportInfo) => unknown) {
    const ids = this.ready() ? this.s.viewportIds() : this.mode === "stack" ? ["stack"] : this.mode === "wsi" ? ["wsi"] : ["ax", "sag", "cor"];
    const infos = this.ready() ? this.s.info() : [];
    // B: main view left, other two stacked on the right, draggable split (#201 feedback)
    const split = this.variant === "B" && ids.length === 3;
    return html`<div class="grid ${split ? "b3" : ids.length === 3 ? "n3" : "n1"}" style=${split ? `--split:${this.splitPct}%` : ""}>
      ${split ? html`<div class="divider" title="Drag to resize" @pointerdown=${this.startSplitDrag}></div>` : nothing}
      ${ids.map((id) => {
        const v = infos.find((i) => i.id === id);
        const main = id === "ax" || ids.length === 1;
        return html`<div class="cell c-${id} ${id === "wsi" ? "wsi-cell" : ""}"
            @dblclick=${split && id !== "ax" ? () => this.s.swapWithMain(id) : null}
            title=${split && id !== "ax" ? "Double-click: show in the big view" : ""}>
          <div class="vp" id=${id} @contextmenu=${(e: Event) => e.preventDefault()}></div>
          ${this.dragKey && main ? this.dropZones() : nothing}
          ${v ? html`
            <div class="ov tl">${v.label}</div>
            ${this.mode === "wsi" ? nothing : html`<div class="ov bl">${v.voi}</div>`}
            ${v.badge && this.variant !== "B" ? html`<div class="ov tr"><span class="badge ${v.badgeLevel}">${v.badgeLevel === "warn" ? "⚠ " : ""}${v.badge}</span><div class="legend">${v.badgeLegend}</div></div>` : nothing}
            ${hud ? hud(v) : nothing}` : nothing}
        </div>`;
      })}
    </div>`;
  }

  @state() private splitPct = (() => {
    try { return Number(localStorage.getItem("mires-viewer-split")) || 66; } catch { return 66; }
  })();

  private startSplitDrag = (e: PointerEvent) => {
    const divider = e.currentTarget as HTMLElement;
    const grid = divider.parentElement!;
    divider.setPointerCapture(e.pointerId);
    const move = (ev: PointerEvent) => {
      const r = grid.getBoundingClientRect();
      this.splitPct = Math.round(Math.min(85, Math.max(25, ((ev.clientX - r.left) / r.width) * 100)));
      this.updateComplete.then(() => this.s.engine.resize(true, true));
    };
    const up = () => {
      divider.removeEventListener("pointermove", move);
      divider.removeEventListener("pointerup", up);
      try { localStorage.setItem("mires-viewer-split", String(this.splitPct)); } catch { /* per-viewer convenience only */ }
    };
    divider.addEventListener("pointermove", move);
    divider.addEventListener("pointerup", up);
    e.preventDefault();
  };

  private toolBtn(t: ToolDef, content: unknown = t.label) {
    return html`<button class=${this.s?.primary === t.id ? "on" : ""} title="${t.label} (${t.key.toUpperCase()})"
      @click=${() => this.s.setPrimary(t.id)}>${content}</button>`;
  }

  private layoutBtns() {
    if (!this.isVol() || !this.ready()) return nothing;
    const l = this.s.layout, o = this.s.orientation;
    const one = (x: "axial" | "sagittal" | "coronal", lbl: string) =>
      html`<button class=${l === "1x1" && o === x ? "on" : ""} @click=${() => this.s.setOrientation(x)}>${lbl}</button>`;
    return html`${one("axial", "Ax")}${one("sagittal", "Sag")}${one("coronal", "Cor")}
      <button class=${l === "1x3" ? "on" : ""} @click=${() => this.s.setLayout("1x3")}>1×3 ✚</button>`;
  }

  private fusionSlider() {
    if (!this.ready() || !this.isVol() || this.s.layers.length < 2) return nothing;
    const i = this.s.layers.length - 1;
    return html`<label style="display:flex;gap:6px;align-items:center">${this.s.layers[i].key} opacity
      <input type="range" min="0" max="1" step="0.05" .value=${String(this.s.layers[i].opacity)}
        @input=${(e: any) => this.s.setLayerOpacity(i, Number(e.target.value))}></label>`;
  }

  // ---------- series list + drag-and-drop (B) ----------
  @state() private dragKey = "";
  @state() private dropZone = "";

  private seriesPanel() {
    if (!this.ready()) return html`<div class="B-series"></div>`;
    const inView = (k: string) => this.s.layers.findIndex((L) => L.key === k);
    return html`<div class="B-series"><h5>Series</h5>
      ${this.s.catalog.map((c) => {
        const n = inView(c.key);
        return html`<div class="ser ${n >= 0 ? "shown" : ""}" draggable="true"
            @dragstart=${(e: DragEvent) => { e.dataTransfer!.setData("text/plain", c.key); e.dataTransfer!.effectAllowed = "copyMove"; this.dragKey = c.key; }}
            @dragend=${() => { this.dragKey = ""; this.dropZone = ""; }}
            @dblclick=${() => this.s.replace(c.key)} title="Drag onto the big view: top half fuses, bottom half replaces. Double-click: replace.">
          <div class="ser-mod">${c.modality}</div>
          <div class="ser-txt"><b>${c.description || c.key}</b><span>${c.count} ${c.volumetric ? "images" : "frames"} · FoR …${c.frameOfReference.slice(-6)}</span></div>
          ${n === 0 ? html`<span class="chip">base</span>` : n > 0 ? html`<span class="chip ov2">overlay</span>` : nothing}
        </div>`;
      })}
      <p class="hint">Drag a series onto the big view.<br>Top half: fuse · bottom half: replace.</p>
    </div>`;
  }

  private dropZones() {
    const key = this.dragKey;
    const zone = (kind: "fuse" | "replace", label: string, why: string) => html`<div
        class="dz-half ${why ? "no" : ""} ${this.dropZone === kind ? "hot" : ""}"
        @dragover=${(e: DragEvent) => { if (why) return; e.preventDefault(); e.dataTransfer!.dropEffect = kind === "fuse" ? "copy" : "move"; this.dropZone = kind; }}
        @dragleave=${() => (this.dropZone = "")}
        @drop=${(e: DragEvent) => { e.preventDefault(); const k = e.dataTransfer!.getData("text/plain") || key; this.dragKey = ""; this.dropZone = ""; kind === "fuse" ? this.s.fuse(k) : this.s.replace(k); }}>
      <b>${label}</b><small>${why || (kind === "fuse" ? `overlay ${key} on all views` : `show only ${key}`)}</small></div>`;
    return html`<div class="dz">${zone("fuse", "⊕ Fuse / overlay", this.s.fuseBlocker(key))}${zone("replace", "⇄ Replace", this.s.replaceBlocker(key))}</div>`;
  }

  private layersPanel() {
    const s = this.s;
    return html`<h5>Layers</h5>
      ${s.layers.map((L, i) => {
        const mod = s.series(L.key).modality;
        const r = s.layerRange(i);
        const lo = r.lower ?? 0, hi = r.upper ?? 0;
        const ww = hi - lo, wc = (hi + lo) / 2;
        const num = (label: string, v: number, set: (x: number) => void, step = 1) => html`<label>${label}
          <input type="number" step=${step} .value=${v.toFixed(step < 1 ? 1 : 0)} @change=${(e: any) => set(Number(e.target.value))}></label>`;
        return html`<div class="layer ${s.activeLayer === i ? "act" : ""}" @click=${() => s.activeLayer !== i && s.setActiveLayer(i)}>
          <div class="lh"><span><b>${L.key}</b> ${s.series(L.key).description}</span>
            ${i === 0 ? html`<span class="chip">base</span>` : html`<button class="x" title="Remove overlay" @click=${(e: Event) => { e.stopPropagation(); s.removeLayer(i); }}>×</button>`}</div>
          <div class="lr"><select @change=${(e: any) => { const p = s.presetsForLayer(i).find((x) => x.id === e.target.value); if (p) { s.setActiveLayer(i); s.applyPreset(p); } e.target.value = ""; }}>
              <option value="">Window preset…</option>${s.presetsForLayer(i).map((p) => html`<option value=${p.id}>${p.label}</option>`)}</select></div>
          <div class="lr nums">${mod === "PT"
            ? html`${num("SUV", lo, (x) => s.setLayerRange(i, x, hi), 0.1)}${num("–", hi, (x) => s.setLayerRange(i, lo, x), 0.1)}`
            : html`${num("W", ww, (x) => s.setLayerRange(i, wc - x / 2, wc + x / 2))}${num("L", wc, (x) => s.setLayerRange(i, x - ww / 2, x + ww / 2))}`}</div>
          <div class="lr"><select @change=${(e: any) => s.setLayerColormap(i, e.target.value)}>
            ${COLORMAPS.map((n) => html`<option value=${n} ?selected=${n === L.colormap}>${n}</option>`)}</select></div>
          ${i > 0 ? html`<div class="lr"><label>Opacity <input type="range" min="0" max="1" step="0.05" .value=${String(L.opacity)} @input=${(e: any) => s.setLayerOpacity(i, Number(e.target.value))}></label></div>` : nothing}
        </div>`;
      })}
      <div class="B-cal" style="color:#8a94a0">Selected layer (blue): right-drag window/level, presets and keys 0–8 apply to it.</div>
      <p><button @click=${() => s.invert()}>Invert</button> <button @click=${() => s.reset()}>Reset view</button></p>`;
  }

  private dropdown(id: string, label: unknown, items: unknown) {
    return html`<div class="dd"><button class=${this.open === id ? "on" : ""} @click=${() => (this.open = this.open === id ? "" : id)}>${label} ▾</button>
      ${this.open === id ? html`<div class="dd-menu" @click=${() => (this.open = "")}>${items}</div>` : nothing}</div>`;
  }

  render() {
    void this.tick;
    const body = this.variant === "B" ? this.renderB() : this.variant === "C" ? this.renderC() : this.renderA();
    return html`${body}<div class="status">${this.mode} · ${this.role} · ${this.status}</div>`;
  }

  // ---------- A: top toolbar ----------
  private renderA() {
    const ts = this.tools();
    const nav = ts.filter((t) => t.group === "navigate");
    const meas = ts.filter((t) => t.group === "measure" || t.group === "annotate");
    const cal = ts.find((t) => t.group === "calibrate");
    const lastMeas = meas.find((t) => t.id === this.s?.primary) ?? meas[0];
    return html`
      <div class="A-bar">
        ${this.isVol() ? html`<div class="A-grp"><label>Layout</label>${this.layoutBtns()}</div>` : nothing}
        <div class="A-grp"><label>Navigate</label>${nav.map((t) => this.toolBtn(t, html`${t.icon} ${t.label}`))}</div>
        ${meas.length ? html`<div class="A-grp"><label>Measure</label>
          ${lastMeas ? this.toolBtn(lastMeas, html`${lastMeas.icon} ${lastMeas.label}`) : nothing}
          ${this.dropdown("meas", "", meas.map((t) => html`<button @click=${() => this.s.setPrimary(t.id)}><span>${t.icon} ${t.label}</span><kbd>${t.key.toUpperCase()}</kbd></button>`))}
        </div>` : nothing}
        ${this.presets().length ? html`<div class="A-grp"><label>Window</label>
          ${this.dropdown("preset", "Presets", this.presets().map((p) => html`<button @click=${() => this.s.applyPreset(p)}><span>${p.label}</span><kbd>${p.key}</kbd></button>`))}
          <button @click=${() => this.s.invert()} title="Invert (I)">Invert</button></div>` : nothing}
        ${this.fusionSlider()}
        ${cal ? html`<div class="A-grp">${this.toolBtn(cal, html`${cal.icon} Calibrate`)}</div>` : nothing}
        <div class="A-grp" style="margin-left:auto"><button @click=${() => this.s.reset()} title="Reset (Esc)">Reset</button>
          ${this.dropdown("help", "?", BINDINGS_HELP.ohif.map((b) => html`<button disabled>${b}</button>`))}</div>
      </div>
      <div class="main">${this.grid()}</div>`;
  }

  // ---------- B: rail + inspector ----------
  private renderB() {
    const ts = this.tools();
    const groups: [string, ToolDef[]][] = [
      ["Nav", ts.filter((t) => t.group === "navigate")],
      ["Measure", ts.filter((t) => t.group === "measure")],
      ["Annot.", ts.filter((t) => t.group === "annotate" || t.group === "calibrate")],
    ];
    const infos = this.ready() ? this.s.info() : [];
    return html`<div class="main">
      ${this.seriesPanel()}
      <div class="B-rail">${groups.filter(([, g]) => g.length).map(([n, g]) => html`<h6>${n}</h6>${g.map((t) => this.toolBtn(t, html`${t.icon}<kbd>${t.key}</kbd>`))}`)}</div>
      ${this.grid()}
      <div class="B-insp">
        ${this.isVol() && this.ready() ? html`<h5>Layout</h5><div class="B-layouts">
          ${(["axial", "sagittal", "coronal"] as const).map((o) => html`<button class=${this.s.layout === "1x1" && this.s.orientation === o ? "on" : ""} @click=${() => this.s.setOrientation(o)}><b>▢</b>${o}</button>`)}
          <button class=${this.s.layout === "1x3" ? "on" : ""} @click=${() => this.s.setLayout("1x3")}><b>▢▤</b>3 views + ✚</button></div><div class="B-cal" style="color:#8a94a0">Double-click a small view to swap it into the big one.</div>` : nothing}
        ${this.isVol() && this.ready() ? this.layersPanel() : this.presets().length ? html`<h5>Window presets</h5><div class="B-presets">
          ${this.presets().map((p) => html`<button @click=${() => this.s.applyPreset(p)}>${p.label} <kbd>${p.key}</kbd></button>`)}</div>
          <p><button @click=${() => this.s.invert()}>Invert</button> <button @click=${() => this.s.reset()}>Reset view</button></p>` : html`<h5>View</h5><button @click=${() => this.s?.reset()}>Reset view</button>`}
        <h5>Measurement units</h5>
        ${infos.map((v) => html`<div class="B-cal"><b>${v.label}</b>: ${v.badge ? html`<span class="badge ${v.badgeLevel}">${v.badge}</span>` : "mm"}<br><span style="color:#8a94a0">${v.badgeLegend}</span></div>`)}
        <h5>Mouse</h5>${BINDINGS_HELP.workstation.map((b) => html`<div class="B-cal">${b}</div>`)}
      </div>
    </div>`;
  }

  // ---------- C: chromeless / keyboard-first ----------
  private renderC() {
    const cur = this.tools().find((t) => t.id === this.s?.primary);
    const hud = (v: ViewportInfo) => html`<div class="C-hud">
      ${this.isVol() && this.ready() && (this.s.layout === "1x3" || v.id === "ax") ? html`${this.layoutBtns()}` : nothing}
      ${this.presets().slice(1, 4).map((p) => html`<button @click=${() => this.s.applyPreset(p)}>${p.label}</button>`)}
    </div>`;
    return html`<div class="main" style="position:relative">
      ${this.grid(hud)}
      <div class="C-pill">${cur ? html`<span>${cur.icon} <b>${cur.label}</b></span><kbd>${cur.key.toUpperCase()}</kbd>` : "…"}
        <span style="color:#7a8591">Space: commands · ?: shortcuts</span></div>
      ${this.open === "palette" ? this.palette() : nothing}
      ${this.open === "sheet" ? this.sheet() : nothing}
    </div>`;
  }

  private commands() {
    const cmds: { label: string; key: string; run: () => void }[] = [];
    this.tools().forEach((t) => cmds.push({ label: `Tool: ${t.label}`, key: t.key.toUpperCase(), run: () => this.s.setPrimary(t.id) }));
    this.presets().forEach((p) => cmds.push({ label: `Window: ${p.label}`, key: p.key, run: () => this.s.applyPreset(p) }));
    if (this.isVol()) {
      (["axial", "sagittal", "coronal"] as const).forEach((o) => cmds.push({ label: `Layout: 1×1 ${o}`, key: "V", run: () => this.s.setOrientation(o) }));
      cmds.push({ label: "Layout: 3 views + crosshairs", key: "V", run: () => this.s.setLayout("1x3") });
    }
    cmds.push({ label: "Invert", key: "I", run: () => this.s.invert() }, { label: "Reset view", key: "Esc", run: () => this.s.reset() });
    return cmds;
  }

  private palette() {
    const q = this.paletteQuery.toLowerCase();
    const list = this.commands().filter((c) => c.label.toLowerCase().includes(q));
    return html`<div class="C-overlay" @click=${() => (this.open = "")}><div class="C-box" @click=${(e: Event) => e.stopPropagation()}>
      <input autofocus placeholder="Type a tool, preset or layout…" .value=${this.paletteQuery}
        @input=${(e: any) => (this.paletteQuery = e.target.value)}
        @keydown=${(e: KeyboardEvent) => { e.stopPropagation(); if (e.key === "Enter" && list[0]) { list[0].run(); this.open = ""; } if (e.key === "Escape") this.open = ""; }}>
      ${list.map((c, i) => html`<div class="row ${i === 0 ? "sel" : ""}" @click=${() => { c.run(); this.open = ""; }}><span>${c.label}</span><kbd>${c.key}</kbd></div>`)}
    </div></div>`;
  }

  private sheet() {
    return html`<div class="C-overlay" @click=${() => (this.open = "")}><div class="C-box"><h4 style="margin:0 0 8px">Shortcuts</h4><div class="C-sheet">
      ${this.commands().map((c) => html`<div><span>${c.label}</span><kbd>${c.key}</kbd></div>`)}
      ${BINDINGS_HELP.ohif.map((b) => html`<div><span>${b}</span></div>`)}
    </div></div></div>`;
  }

  // ---------- keyboard (all variants; C surfaces it) ----------
  private onKey(e: KeyboardEvent) {
    if (!this.ready() || e.metaKey || e.ctrlKey || e.altKey) return;
    const k = e.key.toLowerCase();
    if (this.variant === "C" && k === " ") { this.paletteQuery = ""; this.open = "palette"; e.preventDefault(); return; }
    if (this.variant === "C" && e.key === "?") { this.open = this.open === "sheet" ? "" : "sheet"; return; }
    if (e.key === "Escape") { if (this.open) this.open = ""; else this.s.reset(); return; }
    if (k === "i") return this.s.invert();
    if (k === "v" && this.isVol()) {
      const order = ["axial", "sagittal", "coronal"] as const;
      if (this.s.layout === "1x3") this.s.setOrientation("axial");
      else if (this.s.orientation === "coronal") this.s.setLayout("1x3");
      else this.s.setOrientation(order[order.indexOf(this.s.orientation) + 1]);
      return;
    }
    const t = this.tools().find((x) => x.key === k);
    if (t) return this.s.setPrimary(t.id);
    const p = this.presets().find((x) => x.key === k);
    if (p) this.s.applyPreset(p);
  }
}
