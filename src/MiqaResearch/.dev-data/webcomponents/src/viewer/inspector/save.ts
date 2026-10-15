// Save buttons (#289, spec "Results UI"): at the top of the inspector, one per kind, enabled when there
// are edits; no extra dialog (a toast confirms, a 409 opens the conflict dialog). Ctrl/⌘+S saves both.
// Annotate roles only. Warns when the SR would drop annotations of tools the adapter can't export.
import { html, nothing } from "lit";

import { commands } from "../commands.ts";
import type { ViewerContext } from "../context.ts";
import { OBJECT_KINDS, type ObjectKind } from "../save.ts";
import { droppedTools } from "../sr.ts";
import { tools } from "../tools/index.ts";
import { inspector } from "./registry.ts";

const NOUN: Record<ObjectKind, string> = { annotation: "Annotations", segmentation: "Segmentation" };

function saveButton(ctx: ViewerContext, kind: ObjectKind) {
  const { save } = ctx;
  return html`<button
    data-save=${kind}
    ?disabled=${!save.enabled(kind)}
    aria-busy=${save.saving === kind ? "true" : "false"}
    @click=${() => void save.save(kind)}
  >
    <b>${NOUN[kind]}</b> · ${save.saving === kind ? "Saving…" : save.label(kind)}
  </button>`;
}

inspector.register({
  id: "save",
  order: 10,
  render(ctx) {
    if (!ctx.canAnnotate) return nothing;
    const dropped = droppedTools(ctx.annotationTools).map((id) => tools.byId(id)?.label ?? id);
    return html`<section class="panel save">
      <h5>Save <kbd>Ctrl/⌘ S</kbd></h5>
      <div class="save-buttons">${OBJECT_KINDS.map((kind) => saveButton(ctx, kind))}</div>
      ${dropped.length
        ? html`<div class="hint save-dropped" role="note">Not saved in the Annotations: ${dropped.join(", ")}.</div>`
        : nothing}
      ${ctx.save.error ? html`<div class="hint save-error" role="alert">${ctx.save.error}</div>` : nothing}
    </section>`;
  },
});

commands.register({
  id: "save",
  key: "s",
  ctrlOrMeta: true,
  label: "Save",
  available: (ctx) => ctx.canAnnotate,
  run: (ctx) => void ctx.save.saveAll(),
});
