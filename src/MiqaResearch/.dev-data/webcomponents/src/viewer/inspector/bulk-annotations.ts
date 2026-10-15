// Bulk annotations (ANN, #292) on a slide: one show/hide toggle per annotation group. Read-only:
// algorithm output is never edited in the viewer (user drawing stays the CS3D tools).
import { html, nothing } from "lit";

import { inspector } from "./registry.ts";

inspector.register({
  id: "bulk-annotations",
  order: 35,
  render(ctx) {
    if (ctx.viewport !== "wsi" || !ctx.bulkAnnotationGroups.length) return nothing;
    return html`<section class="panel" data-panel="bulk-annotations">
      <h5>Bulk annotations</h5>
      ${ctx.bulkAnnotationGroups.map(
        (g) => html`<label class="row" title=${`${g.count} ${g.graphicType.toLowerCase()}`}>
          <input
            type="checkbox"
            data-ann-group=${g.uid}
            .checked=${g.visible}
            @change=${(e: Event) => ctx.setBulkAnnotationGroupVisible(g.uid, (e.target as HTMLInputElement).checked)}
          />
          ${g.name} <span class="hint">(${g.count})</span>
        </label>`,
      )}
      <div class="hint">Algorithm output · read-only</div>
    </section>`;
  },
});
