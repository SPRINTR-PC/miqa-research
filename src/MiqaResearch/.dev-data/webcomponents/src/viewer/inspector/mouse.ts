// Workstation mouse help for the current viewport kind.
import { html } from "lit";

import { MOUSE_HELP } from "../tools/index.ts";
import { inspector } from "./registry.ts";

inspector.register({
  id: "mouse",
  order: 90,
  render: (ctx) => html`<section class="panel">
    <h5>Mouse</h5>
    ${MOUSE_HELP[ctx.viewport].map((line) => html`<div class="hint">${line}</div>`)}
  </section>`,
});
