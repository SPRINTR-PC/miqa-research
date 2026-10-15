// Layers (#284): the volume view's layers (base + fused overlays). Select one (it gets right-drag W/L
// and the preset keys), remove an overlay, and set the selected layer's colormap, opacity multiplier
// and opacity transfer curve (breakpoints in data units). Also reduced 3D's colormap control (#283).
// SUV: a PET shown in Bq/ml (SUV scaling not applied) is flagged here, on volumes and on the stack.
import { html, nothing, svg } from "lit";

import type { LayerState } from "../adapter/adapter.ts";
import { addCurvePoint, COLORMAPS, removeCurvePoint, setCurvePoint, type OpacityPoint } from "../fusion.ts";
import { suvWarning } from "../suv.ts";
import { voiToWindow } from "../tools/index.ts";
import { inspector } from "./registry.ts";

const suvShown = (l: LayerState) => l.modality === "PT" && !!l.suv?.applied;

/** Data unit of a layer's values: SUV, Bq/ml (PET without SUV) or the modality's (HU for CT). */
function unit(l: LayerState): string {
  if (l.modality === "PT") return suvShown(l) ? "SUV" : "Bq/ml";
  return l.modality === "CT" ? "HU" : "";
}

function windowText(l: LayerState): string {
  if (!l.voi) return "image default";
  const round = (n: number) => (Math.abs(n) < 100 ? Number(n.toFixed(2)) : Math.round(n));
  if (suvShown(l)) return `SUV ${round(l.voi.lower)}–${round(l.voi.upper)}`;
  const { width, center } = voiToWindow(l.voi);
  return `W ${round(width)} L ${round(center)}`;
}

function warning(l: { seriesUid: string; suv?: LayerState["suv"] }) {
  const text = suvWarning(l.suv);
  return text ? html`<div class="badge suv-warning" data-level="warn" role="note" data-series-uid=${l.seriesUid}>⚠ ${text}</div>` : nothing;
}

/** The curve as a polyline over its value range (opacity up), for a glance at its shape. */
function curvePreview(curve: OpacityPoint[]) {
  if (curve.length < 2) return nothing;
  const lo = curve[0].value;
  const span = curve[curve.length - 1].value - lo || 1;
  const points = curve.map((p) => `${((p.value - lo) / span) * 100},${30 - p.opacity * 28}`).join(" ");
  return html`<svg class="curve" viewBox="-2 0 104 32" width="100%" height="32" role="img" aria-label="Opacity curve">
    ${svg`<rect x="-2" y="0" width="104" height="32" fill="#0b0d10"></rect>
      <polyline points=${points} fill="none" stroke="#1f6feb" stroke-width="1.5"></polyline>`}
  </svg>`;
}

function curveEditor(l: LayerState, set: (curve: OpacityPoint[]) => void) {
  const u = unit(l);
  const number = (e: Event) => Number((e.target as HTMLInputElement).value);
  return html`<h5>Opacity curve${u ? ` (${u})` : ""}</h5>
    ${curvePreview(l.curve)}
    ${l.curve.length ? nothing : html`<div class="hint">Flat: every value at the opacity above.</div>`}
    ${l.curve.map(
      (p, i) => html`<div class="row curve-point">
        <input type="number" step="any" style="width: 64px" data-curve-value=${i} aria-label="Value" .value=${String(p.value)}
          @change=${(e: Event) => set(setCurvePoint(l.curve, i, { value: number(e), opacity: p.opacity }))} />
        <input type="number" min="0" max="100" step="5" style="width: 52px" data-curve-opacity=${i} aria-label="Opacity %"
          .value=${String(Math.round(p.opacity * 100))}
          @change=${(e: Event) => set(setCurvePoint(l.curve, i, { value: p.value, opacity: number(e) / 100 }))} />%
        <button data-curve-remove=${i} title="Remove breakpoint" @click=${() => set(removeCurvePoint(l.curve, i))}>×</button>
      </div>`,
    )}
    <div class="row">
      <button data-curve-add @click=${() => {
        const last = l.curve[l.curve.length - 1];
        set(addCurvePoint(l.curve, { value: last ? last.value + 1 : 0, opacity: 1 }));
      }}>Add breakpoint</button>
    </div>`;
}

inspector.register({
  id: "layers",
  order: 30,
  render(ctx) {
    if (ctx.layout.kind !== "volume" || !ctx.layers.length) {
      const w = warning({ seriesUid: "", suv: ctx.suv });
      return w === nothing ? nothing : html`<section class="panel"><h5>Units</h5>${w}</section>`;
    }
    const { layers } = ctx;
    const selected = layers.find((l) => l.seriesUid === ctx.selectedLayer) ?? layers[0];
    const base = selected === layers[0];
    const opacity = Math.round(selected.opacity * 100);
    return html`<section class="panel layers">
      <h5>Layers</h5>
      ${layers.map(
        (l, i) => html`<div class="row">
            <button style="flex: 1; text-align: left" data-layer=${l.seriesUid} aria-pressed=${l === selected ? "true" : "false"}
              title="Select: right-drag and preset keys window this layer" @click=${() => ctx.selectLayer(l.seriesUid)}>
              ${i === 0 ? "▣" : "⊕"} ${l.label}
            </button>
            ${i > 0 ? html`<button data-remove-layer=${l.seriesUid} title="Remove from the views" @click=${() => ctx.removeLayer(l.seriesUid)}>×</button>` : nothing}
          </div>
          ${warning(l)}`,
      )}
      ${layers.length > 1 ? html`<div class="hint">Right-drag and preset keys window the selected layer.</div>` : nothing}
      <h5>${selected.label}</h5>
      <div class="hint" data-layer-window>Window: ${windowText(selected)}</div>
      <div class="row">
        <label>Colormap
          <select data-colormap @change=${(e: Event) => ctx.setLayerDisplay(selected.seriesUid, { colormap: (e.target as HTMLSelectElement).value })}>
            ${COLORMAPS.map((name) => html`<option value=${name} ?selected=${name === selected.colormap}>${name}</option>`)}
          </select>
        </label>
      </div>
      ${base
        ? nothing
        : html`<div class="row">
              <label>Opacity
                <input type="range" min="0" max="100" step="5" data-opacity .value=${String(opacity)}
                  @input=${(e: Event) => ctx.setLayerDisplay(selected.seriesUid, { opacity: Number((e.target as HTMLInputElement).value) / 100 })} />
                ${opacity}%
              </label>
            </div>
            ${curveEditor(selected, (curve) => ctx.setLayerDisplay(selected.seriesUid, { curve }))}`}
    </section>`;
  },
});
