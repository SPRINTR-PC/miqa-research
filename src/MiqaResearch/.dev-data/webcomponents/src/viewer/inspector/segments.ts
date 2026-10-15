// Segments (#286): the Segmentation's segment list (add, rename, colour, set active), brush size, and
// the Rectangle ROI threshold form. Annotate roles, stacks and full-resolution volumes only.
import { html, nothing } from "lit";

import type { ViewerContext } from "../context.ts";
import { defaultThresholdRange, hexToRgb, rgbToHex } from "../segmentation.ts";
import { BRUSH, ERASER, POLYGON, THRESHOLD, eraseTwin } from "../tools/segmentation.ts";
import { inspector } from "./registry.ts";

const input = (e: Event) => e.target as HTMLInputElement;

function thresholdForm(ctx: ViewerContext) {
  const { modality } = ctx.thresholdLayer;
  const range = defaultThresholdRange(modality);
  const unit = modality === "PT" ? "SUV" : modality === "CT" ? "HU" : "value";
  const drawn = ctx.segmentation?.thresholdRectangles ?? 0;
  const run = (e: Event) => {
    e.preventDefault();
    const form = e.target as HTMLFormElement;
    const value = (name: string) => Number((form.elements.namedItem(name) as HTMLInputElement).value);
    ctx.runThreshold({ lower: value("lower"), upper: value("upper") }, Math.max(0, Math.round(value("slices"))));
  };
  return html`<form class="threshold" @submit=${run}>
    <div class="hint">Draw rectangles, then fill the active segment where the ${modality || "base"} series is in range.</div>
    <div class="row">
      <label>${unit} <input name="lower" type="number" step="any" value=${range.lower} style="width: 64px" /></label>
      <label>– <input name="upper" type="number" step="any" value=${range.upper} style="width: 64px" /></label>
    </div>
    <div class="row">
      <label>± slices <input name="slices" type="number" min="0" step="1" value="0" style="width: 48px" /></label>
      <button type="submit" data-action="threshold" ?disabled=${!drawn}>Run threshold</button>
    </div>
    ${ctx.thresholdResult === undefined
      ? nothing
      : html`<div class="hint threshold-result">Last run: ${ctx.thresholdResult} voxels filled.</div>`}
  </form>`;
}

function toolHint(tool: string) {
  if (tool === POLYGON) {
    return "Click vertices; double-click or click the first one to close and fill. Right button: erase the active segment inside.";
  }
  return eraseTwin(tool) ? "Right-drag erases with the same shape." : undefined;
}

inspector.register({
  id: "segments",
  order: 25,
  render(ctx) {
    const reduced = ctx.layout.kind === "volume" && !!ctx.layout.reduced;
    if (!ctx.canAnnotate || ctx.viewport === "wsi" || reduced) return nothing;
    const seg = ctx.segmentation;
    const view = ctx.segmentationView;
    if (!seg || !view) {
      return html`<section class="panel segments">
        <h5>Segmentation</h5>
        <button data-action="new-segmentation" ?disabled=${!ctx.view} @click=${() => void ctx.ensureSegmentation()}>
          New segmentation
        </button>
        <div class="hint">Or pick a segment tool. The Segmentation is on the base series' grid.</div>
      </section>`;
    }
    const tool = ctx.activeTool;
    const hint = toolHint(tool);
    return html`<section class="panel segments">
      <h5>Segmentation</h5>
      ${seg.segments.map(
        (s) => html`<div class="row" data-segment=${s.index}>
          <button data-action="activate" aria-pressed=${s.index === seg.active ? "true" : "false"} title="Paint this segment"
            @click=${() => view.setActiveSegment(s.index)}>${s.index}</button>
          <input type="color" aria-label="Colour of ${s.label}" .value=${rgbToHex(s.color)}
            @change=${(e: Event) => view.setSegmentColor(s.index, hexToRgb(input(e).value))} style="width: 28px; padding: 0" />
          <input type="text" aria-label="Name of segment ${s.index}" .value=${s.label}
            @change=${(e: Event) => view.renameSegment(s.index, input(e).value)} style="flex: 1; min-width: 0" />
        </div>`,
      )}
      <div class="row"><button data-action="add-segment" @click=${() => view.addSegment()}>+ Segment</button></div>
      ${tool === BRUSH || tool === ERASER
        ? html`<div class="row"><label>Brush size
            <input name="brush-size" type="range" min="1" max="50" .value=${String(seg.brushSize)}
              @input=${(e: Event) => view.setBrushSize(Number(input(e).value))} /> ${seg.brushSize}</label></div>`
        : nothing}
      ${tool === THRESHOLD ? thresholdForm(ctx) : nothing}
      ${hint ? html`<div class="hint">${hint}</div>` : nothing}
    </section>`;
  },
});
