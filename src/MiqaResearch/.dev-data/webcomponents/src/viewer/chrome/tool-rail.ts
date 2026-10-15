// Tool rail (Nav / Measure / Annot. / Segment), rendered from the tool registry.
import { html } from "lit";

import type { RailGroup } from "../tools/index.ts";

export function toolRail(groups: RailGroup[], activeTool: string, select: (toolId: string) => void) {
  return html`<nav class="rail" aria-label="Tools">
    ${groups.map(
      (g) => html`<h6>${g.label}</h6>
        ${g.tools.map(
          (t) => html`<button
            data-tool=${t.id}
            aria-pressed=${t.id === activeTool ? "true" : "false"}
            title="${t.label} (${t.key.toUpperCase()})"
            @click=${() => select(t.id)}
          >
            ${t.icon}<kbd>${t.key.toUpperCase()}</kbd>
          </button>`,
        )}`,
    )}
  </nav>`;
}
