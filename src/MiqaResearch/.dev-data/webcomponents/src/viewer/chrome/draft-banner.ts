// Draft recovery banner (#291): over the view on open, one row per unsaved draft found (Annotations,
// Segmentation), naming when it was autosaved and the version it was based on, with Restore / Discard.
import { css, html, nothing } from "lit";

import type { Draft } from "../drafts.ts";
import type { ObjectKind } from "../save.ts";

export const draftBannerStyles = css`
  .draft-banner { position: absolute; z-index: 7; top: 76px; left: 50%; transform: translateX(-50%); max-width: 80%;
    display: flex; flex-direction: column; gap: 4px; padding: 6px 10px; border-radius: 4px; font-size: 12px;
    background: #16233a; border: 1px solid #2f4a6b; color: #cfe0f5; }
  .draft-banner .draft { display: flex; gap: 8px; align-items: center; }
  .draft-banner .draft span { flex: 1; }
  .draft-banner button { padding: 0 8px; }
  .draft-banner .draft-error { color: #ffb0b0; }
`;

const NOUN: Record<ObjectKind, string> = { annotation: "Annotations", segmentation: "Segmentation" };

export function draftBanner(
  drafts: Draft[],
  error: string,
  restore: (kind: ObjectKind) => void,
  discard: (kind: ObjectKind) => void,
) {
  if (!drafts.length && !error) return nothing;
  return html`<div class="draft-banner" role="status">
    ${drafts.map((d) => {
      const when = new Date(d.savedAt).toLocaleString();
      const base = d.base ? html`, on v${d.base.head.version}` : html`, not saved before`;
      return html`<div class="draft" data-draft=${d.kind}>
        <span>Unsaved ${NOUN[d.kind]} from ${when}${base}.</span>
        <button data-draft-restore=${d.kind} @click=${() => restore(d.kind)}>Restore</button>
        <button data-draft-discard=${d.kind} @click=${() => discard(d.kind)}>Discard</button>
      </div>`;
    })}
    ${error ? html`<div class="draft-error">${error}</div>` : nothing}
  </div>`;
}
