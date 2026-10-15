// Save feedback over the view (#289): the toast confirming a save, and the 409 dialog when someone
// else saved a newer version first. The buttons live in the inspector (../inspector/save.ts).
import { css, html, nothing } from "lit";

import type { Conflict, ConflictChoice } from "../save.ts";

export const saveDialogStyles = css`
  .toast { position: absolute; left: 50%; bottom: 16px; transform: translateX(-50%); z-index: 20; padding: 6px 12px; border-radius: 4px; background: #1d3b2a; border: 1px solid #2f6b4a; color: #c8f0d8; }
  .conflict-backdrop { position: absolute; inset: 0; z-index: 30; background: rgb(0 0 0 / 0.55); display: grid; place-items: center; }
  .conflict { width: min(420px, calc(100% - 32px)); background: #151a21; border: 1px solid #3b4654; border-radius: 6px; padding: 14px 16px; }
  .conflict h4 { margin: 0 0 8px; font-size: 14px; }
  .conflict p { margin: 0 0 12px; color: #aab4bf; line-height: 1.45; }
  .conflict .choices { display: flex; flex-direction: column; gap: 6px; }
  .conflict .choices button { text-align: left; }
`;

const KIND: Record<Conflict["kind"], string> = { annotation: "Annotations", segmentation: "Segmentation" };

export function toast(message: string) {
  return message ? html`<div class="toast" role="status">${message}</div>` : nothing;
}

/** Who saved which version and when; three outcomes ("Save mine on top" only if allowed), no merge. */
export function conflictDialog(
  conflict: Conflict | undefined,
  busy: boolean,
  choose: (choice: ConflictChoice) => void,
  dismiss: () => void,
) {
  if (!conflict) return nothing;
  const { head } = conflict;
  const when = new Date(head.created_at).toLocaleString();
  return html`<div class="conflict-backdrop">
    <div class="conflict" role="dialog" aria-modal="true" aria-labelledby="conflict-title">
      <h4 id="conflict-title">${KIND[conflict.kind]}: a newer version was saved</h4>
      <p>${head.author ?? "Someone"} saved v${head.version} on ${when}, after the version you edited. Your edits are kept until you choose.</p>
      <div class="choices">
        <button data-choice="load-theirs" ?disabled=${busy} @click=${() => choose("load-theirs")}>Discard mine, load theirs</button>
        <button data-choice="separate" ?disabled=${busy} @click=${() => choose("separate")}>Save mine as a separate object</button>
        ${conflict.canChange
          ? html`<button data-choice="on-top" ?disabled=${busy} @click=${() => choose("on-top")}>Save mine on top (v${head.version + 1})</button>`
          : nothing}
        <button data-choice="cancel" ?disabled=${busy} @click=${dismiss}>Not now</button>
      </div>
    </div>
  </div>`;
}
