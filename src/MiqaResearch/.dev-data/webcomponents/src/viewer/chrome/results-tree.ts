// Results tree templates (#290): result rows under each series (click to show / hide, ⋯ for History and
// Retire), the Blinded Annotation lock row on top, the "Show retired" footer, the chips over the viewport
// and the confirm dialog (Retire, Blinding Reveal). State and actions are the ResultsController's (../results.ts).
import { css, html, nothing } from "lit";

import { NOUN, kindOf, showable, type ResultChain, type ResultVersion, type ResultsController } from "../results.ts";

export const resultsTreeStyles = css`
  .results { margin: -2px 0 6px 12px; display: flex; flex-direction: column; gap: 2px; }
  .result { position: relative; display: flex; align-items: center; gap: 4px; padding: 3px 4px; border: 1px solid #262c35; border-radius: 3px; background: #12171d; font-size: 11px; }
  .result.shown { background: #1a2a1f; border-color: #2f6b4a; }
  .result.retired { opacity: 0.55; }
  .result .show { flex: 1; min-width: 0; display: flex; gap: 4px; align-items: center; text-align: left; background: none; border: 0; padding: 0; }
  .result .show:disabled { opacity: 1; }
  .result .show span { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .result .icon { width: 12px; text-align: center; }
  .result small { color: #7a8591; }
  .result .fusion { font: 10px ui-monospace, monospace; background: #2b323c; border-radius: 3px; padding: 0 3px; }
  .result .more { padding: 0 5px; }
  .result-menu { position: absolute; right: 0; top: 100%; z-index: 10; display: flex; flex-direction: column; background: #151a21; border: 1px solid #3b4654; border-radius: 4px; padding: 2px; }
  .result-menu button { text-align: left; border: 0; }
  .result-history { margin: 0 0 2px 16px; padding: 4px 6px; border-left: 2px solid #2b323c; font-size: 11px; list-style: none; }
  .result-history li { color: #aab4bf; }
  .result-history li.head { color: #d8dde3; font-weight: 600; }
  .lock-row { margin: 0 0 6px; padding: 6px; border: 1px solid #8a5a14; border-radius: 4px; background: #2a1f10; color: #ffcf7a; font-size: 11px; line-height: 1.4; }
  .lock-row button { margin-top: 4px; }
  .results-footer { margin: 8px 0; font-size: 11px; color: #8a94a0; display: flex; gap: 4px; align-items: center; }
  .chips { position: absolute; top: 8px; left: 50%; transform: translateX(-50%); z-index: 6; display: flex; gap: 4px; flex-wrap: wrap; justify-content: center; max-width: 70%; }
  .chip { display: flex; gap: 4px; align-items: center; padding: 1px 2px 1px 8px; border-radius: 10px; background: rgb(21 26 33 / 0.85); border: 1px solid #2f6b4a; font-size: 11px; }
  .chip button { border: 0; background: none; padding: 0 5px; border-radius: 10px; }
`;

const ICON: Record<string, string> = { annotation: "📏", segmentation: "🖌" };

const when = (iso: string) => new Date(iso).toLocaleString();

/** "Annotations v2 · anna": what a row and a chip say. */
export function summary(chain: ResultVersion): string {
  const noun = chain.modality === "SR" || chain.modality === "SEG" ? NOUN[kindOf(chain)] : (chain.series_description ?? chain.modality ?? "");
  return `${noun} v${chain.version}`;
}

/** "⊕ PT": the other sources of an object made on a Fusion; undefined for one source. */
export function fusionBadge(chain: ResultVersion, modalityOf: (seriesUid: string) => string): string | undefined {
  const base = chain.base_series_uid ?? chain.source_series_uids[0];
  const others = chain.source_series_uids.filter((uid) => uid !== base);
  if (!others.length) return undefined;
  return `⊕ ${others.map((uid) => modalityOf(uid) || "?").join(" ")}`;
}

function historyList(chain: ResultChain) {
  return html`<ol class="result-history" aria-label="History">
    ${[...chain.history].reverse().map(
      (v) => html`<li class=${v.id === chain.id ? "head" : ""} data-version=${v.version}>
        v${v.version} · ${v.author ?? "ingested"} · ${when(v.created_at)}${v.id === chain.id ? " (current)" : ""}
      </li>`,
    )}
  </ol>`;
}

function resultRow(results: ResultsController, chain: ResultChain, modalityOf: (uid: string) => string, canAnnotate: boolean) {
  const shown = results.shown.has(chain.chain_id);
  const badge = fusionBadge(chain, modalityOf);
  const canShow = showable(chain);
  const title = chain.retired ? "Retired (read-only)" : canShow ? (shown ? "Hide" : "Show") : "Can't be shown in the viewer";
  return html`<div class="result ${shown ? "shown" : ""} ${chain.retired ? "retired" : ""}" data-chain=${chain.chain_id}
      aria-busy=${results.busy === chain.chain_id ? "true" : "false"}>
      <button class="show" title=${title} aria-pressed=${shown ? "true" : "false"} ?disabled=${!canShow || !!results.busy}
        @click=${() => void results.toggle(chain)}>
        <span class="icon">${ICON[kindOf(chain)]}</span>
        <span>${summary(chain)}${chain.retired ? " (retired)" : ""} <small>${chain.author ?? "ingested"}</small></span>
        ${badge ? html`<span class="fusion" title="Made on a Fusion">${badge}</span>` : nothing}
      </button>
      <button class="more" title="More" aria-haspopup="menu" aria-expanded=${results.menu === chain.chain_id ? "true" : "false"}
        @click=${() => results.openMenu(chain.chain_id)}>⋯</button>
      ${results.menu === chain.chain_id
        ? html`<div class="result-menu" role="menu">
            <button role="menuitem" data-action="history" @click=${() => results.openHistory(chain.chain_id)}>History</button>
            ${canAnnotate && chain.can_change && !chain.retired
              ? html`<button role="menuitem" data-action="retire" @click=${() => results.ask({ action: "retire", chain })}>Retire…</button>`
              : nothing}
          </div>`
        : nothing}
    </div>
    ${results.history === chain.chain_id ? historyList(chain) : nothing}`;
}

/** The rows under one series. */
export function resultRows(results: ResultsController, seriesUid: string, modalityOf: (uid: string) => string, canAnnotate: boolean) {
  const rows = results.rows(seriesUid);
  if (!rows.length) return nothing;
  return html`<div class="results">${rows.map((c) => resultRow(results, c, modalityOf, canAnnotate))}</div>`;
}

/** Blinded Annotation: what's hidden, and the Blinding Reveal for PI, Site PI and Admin. */
export function lockRow(results: ResultsController) {
  const b = results.blinding;
  if (!b?.blinded) return nothing;
  if (b.revealed) return html`<div class="lock-row" role="note">🔓 Blinding Reveal active: showing everyone's work for this participant.</div>`;
  return html`<div class="lock-row" role="note">
    🔒 Blinded project — showing only your own work. <b class="hidden-count">${b.hidden}</b> hidden.
    ${b.can_reveal
      ? html`<div><button data-action="reveal" @click=${() => results.ask({ action: "reveal" })}>Reveal for this participant…</button></div>`
      : nothing}
  </div>`;
}

/** "Show retired", read-only, for those who may retire (annotate roles: authors retire their own). */
export function resultsFooter(results: ResultsController, canAnnotate: boolean) {
  return html`${results.error ? html`<p class="hint results-error" role="alert">${results.error}</p>` : nothing}
    ${canAnnotate && results.loaded
      ? html`<label class="results-footer">
          <input type="checkbox" class="show-retired" .checked=${results.showRetired}
            @change=${(e: Event) => void results.setShowRetired((e.target as HTMLInputElement).checked)} />
          Show retired
        </label>`
      : nothing}`;
}

/** Chips over the viewport: what's shown, ✕ to hide. */
export function resultChips(results: ResultsController) {
  if (!results.shown.size) return nothing;
  return html`<div class="chips" aria-label="Shown results">
    ${[...results.shown.values()].map(
      (c) => html`<span class="chip" data-chain=${c.chain_id}>
        ${ICON[kindOf(c)]} ${summary(c)} · ${c.author ?? "ingested"}
        <button title="Hide" aria-label="Hide ${summary(c)}" @click=${() => results.hide(c.chain_id)}>✕</button>
      </span>`,
    )}
  </div>`;
}

const CONFIRM = {
  retire: (chain: ResultChain) => ({
    title: `Retire ${summary(chain)}?`,
    text: "It disappears from lists and counts. It's kept, with its history: nothing is deleted.",
    ok: "Retire",
  }),
  reveal: () => ({
    title: "Reveal everyone's work for this participant?",
    text: "You'll see all Annotations and Segmentations of this participant for this viewer session. The Blinding Reveal is audit-logged.",
    ok: "Reveal",
  }),
};

/** Confirm for Retire and the Blinding Reveal. */
export function resultsConfirm(results: ResultsController) {
  const pending = results.pending;
  if (!pending) return nothing;
  const c = pending.action === "retire" ? CONFIRM.retire(pending.chain) : CONFIRM.reveal();
  const busy = !!results.busy;
  return html`<div class="conflict-backdrop">
    <div class="conflict results-confirm" role="dialog" aria-modal="true" aria-labelledby="results-confirm-title">
      <h4 id="results-confirm-title">${c.title}</h4>
      <p>${c.text}</p>
      <div class="choices">
        <button data-confirm="ok" ?disabled=${busy} @click=${() => void results.confirm()}>${c.ok}</button>
        <button data-confirm="cancel" ?disabled=${busy} @click=${() => results.cancel()}>Cancel</button>
      </div>
    </div>
  </div>`;
}
