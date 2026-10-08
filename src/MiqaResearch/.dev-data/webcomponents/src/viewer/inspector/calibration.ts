// Calibration legend (#281): the spacing type of the viewport, hidden for plain tomographic mm;
// plus the known-length form after a Calibrate line is drawn.
import { html, nothing } from "lit";

import { calibrationLegend } from "../calibration.ts";
import type { ViewerContext } from "../context.ts";
import { inspector } from "./registry.ts";

function knownLengthForm(ctx: ViewerContext) {
  const pending = ctx.stack?.pendingCalibration;
  const view = ctx.stackView;
  if (!pending || !view) return undefined;
  const submit = (e: Event) => {
    e.preventDefault();
    const mm = Number((e.target as HTMLFormElement).querySelector("input")!.value);
    if (mm > 0) view.calibrate?.(mm);
  };
  return html`<form @submit=${submit}>
    <div class="hint">Line measures ${+pending.length.toFixed(2)} ${pending.unit}. Its true length:</div>
    <div class="row">
      <input name="known-length" type="number" min="0" step="any" required aria-label="Known length in mm" style="width: 70px" />
      mm
      <button type="submit">Apply</button>
      <button type="button" data-action="cancel" @click=${() => view.cancelCalibration?.()}>Cancel</button>
    </div>
  </form>`;
}

inspector.register({
  id: "calibration",
  order: 40,
  render(ctx) {
    const legend = ctx.stack ? calibrationLegend(ctx.stack.unit, ctx.image) : undefined;
    const form = knownLengthForm(ctx);
    if (!legend && !form) return nothing;
    const canCalibrate = ctx.canAnnotate && ctx.viewport === "stack" && !form;
    return html`<section class="panel calibration">
      <h5>Calibration</h5>
      ${legend
        ? html`<div class="row"><span class="badge" data-level=${legend.level}>${legend.badge}</span></div>
            <div class="hint">${legend.text}</div>`
        : nothing}
      ${canCalibrate ? html`<div class="hint">Calibrate against a known length: <kbd>C</kbd></div>` : nothing}
      ${form ?? nothing}
    </section>`;
  },
});
