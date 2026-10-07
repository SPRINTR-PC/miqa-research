// Window presets for the series' modality (keys 0–8), Invert (I) and Reset view (Esc).
import { html, nothing } from "lit";

import { presets } from "../tools/index.ts";
import { inspector } from "./registry.ts";

inspector.register({
  id: "window",
  order: 50,
  render(ctx) {
    if (ctx.viewport === "wsi") return nothing;
    const list = presets.forModality(ctx.modality);
    return html`<section class="panel">
      <h5>Window presets</h5>
      <div class="grid2">
        ${list.map(
          (p) => html`<button data-preset=${p.id} ?disabled=${!ctx.view} @click=${() => ctx.applyPreset(p)}>
            ${p.label} <kbd>${p.key}</kbd>
          </button>`,
        )}
      </div>
      <div class="row">
        <button ?disabled=${!ctx.view} @click=${() => ctx.view?.toggleInvert()}>Invert <kbd>I</kbd></button>
        <button ?disabled=${!ctx.view} @click=${() => ctx.view?.resetView()}>Reset view <kbd>Esc</kbd></button>
      </div>
    </section>`;
  },
});
