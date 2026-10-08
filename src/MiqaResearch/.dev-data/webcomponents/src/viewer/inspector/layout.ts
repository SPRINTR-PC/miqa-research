// Layout (#282): acquired stack, one orientation (V cycles), or three views with crosshairs.
// MPR only for a reconstructable series (OHIF rule); otherwise the panel says why.
import { html, nothing } from "lit";

import { ORIENTATIONS, threeViews, type Orientation, type ViewLayout } from "../layout.ts";
import { inspector } from "./registry.ts";

const LABEL: Record<Orientation, string> = { axial: "Axial", sagittal: "Sagittal", coronal: "Coronal" };

inspector.register({
  id: "layout",
  order: 20,
  render(ctx) {
    if (ctx.viewport === "wsi" || !ctx.mpr) return nothing;
    if (!ctx.mpr.ok) {
      return html`<section class="panel">
        <h5>Layout</h5>
        <div class="hint layout-hint">3D views unavailable: ${ctx.mpr.reason}.</div>
      </section>`;
    }
    const { layout } = ctx;
    const shown = layout.kind === "volume" ? layout.orientations : [];
    const button = (id: string, label: string, next: ViewLayout, pressed: boolean, key?: string) =>
      html`<button data-layout=${id} aria-pressed=${pressed ? "true" : "false"} ?disabled=${!ctx.view}
        @click=${() => ctx.setLayout(next)}>${label}${key ? html` <kbd>${key}</kbd>` : nothing}</button>`;
    return html`<section class="panel">
      <h5>Layout</h5>
      <div class="grid2">
        ${button("stack", "Stack", { kind: "stack" }, layout.kind === "stack")}
        ${ORIENTATIONS.map((o) =>
          button(o, LABEL[o], { kind: "volume", orientations: [o] }, shown.length === 1 && shown[0] === o, shown.length === 1 ? "V" : undefined),
        )}
        ${button("three", "3 views ⌖", { kind: "volume", orientations: threeViews(shown[0] ?? "axial") }, shown.length === 3)}
      </div>
      ${shown.length === 3 ? html`<div class="hint">Double-click a small view to swap it into the big one.</div>` : nothing}
    </section>`;
  },
});
