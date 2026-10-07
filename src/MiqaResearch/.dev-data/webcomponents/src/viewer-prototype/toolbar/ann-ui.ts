// PROTOTYPE — throwaway. Ticket #202 (map #176): three structurally different UIs for
// listing/loading Annotations & Segmentations, Supersede/Retire, 409, Blinding Reveal and
// draft recovery, mounted inside the #201 chrome B (series list + rail + inspector).
//   A — Tree: objects nest under their source series in the left series list.
//   B — Inspector tab: a "Results" tab in the right panel, table per kind with history.
//   C — Chips + Open dialog: loaded objects as chips over the viewer; a full browser dialog.
import { css, html, nothing } from "lit";
import type { AnnStore, Kind, Obj } from "./ann-store.js";

export const annCss = css`
  .ann-row { display: flex; align-items: center; gap: 5px; padding: 3px 4px 3px 14px; font-size: 11px; border-radius: 4px; cursor: pointer; }
  .ann-row:hover { background: #1b2027; }
  .ann-row.on { background: #1f6feb33; }
  .ann-row .k { width: 16px; text-align: center; }
  .ann-row .t { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .ann-row small, .muted { color: #7a8591; }
  .ann-row button, .mini { font-size: 10px; padding: 0 5px; }
  .ann-hist { margin: 0 0 4px 32px; border-left: 2px solid #2b323c; padding-left: 6px; font-size: 10px; color: #9aa4b0; }
  .ann-hist div { padding: 1px 0; }
  .lock { margin: 6px 0; padding: 5px 6px; border: 1px dashed #6b5a2a; border-radius: 4px; color: #e8c46a; font-size: 11px; }
  .draft { position: absolute; top: 8px; left: 50%; transform: translateX(-50%); z-index: 25; background: #3a2f12; border: 1px solid #c90; color: #ffe; border-radius: 6px; padding: 6px 10px; display: flex; gap: 8px; align-items: center; font-size: 12px; }
  .toast { position: absolute; bottom: 64px; left: 50%; transform: translateX(-50%); z-index: 50; background: #1f6feb; color: #fff; border-radius: 6px; padding: 6px 12px; font-size: 12px; }
  .loaded-note { position: absolute; bottom: 6px; right: 8px; z-index: 6; font-size: 11px; color: #9fd; background: #000a; padding: 2px 6px; border-radius: 3px; pointer-events: none; }
  .tabs { display: flex; gap: 2px; margin: -8px -10px 6px; border-bottom: 1px solid #262c35; }
  .tabs button { flex: 1; border: 0; border-radius: 0; background: none; padding: 7px; color: #8a94a0; }
  .tabs button.on { color: #fff; border-bottom: 2px solid #1f6feb; background: none; }
  table.res { width: 100%; border-collapse: collapse; font-size: 11px; }
  table.res td { padding: 3px 2px; border-bottom: 1px solid #1b2027; vertical-align: top; }
  table.res tr.on td { background: #1f6feb22; }
  .chips { position: absolute; top: 6px; left: 8px; right: 8px; z-index: 7; display: flex; gap: 6px; flex-wrap: wrap; pointer-events: none; }
  .chip2 { pointer-events: auto; background: #141920e6; border: 1px solid #2f6fd8; border-radius: 999px; padding: 2px 8px; font-size: 11px; display: flex; gap: 6px; align-items: center; }
  .chip2.add { border-style: dashed; border-color: #556; cursor: pointer; }
  .chip2 b { font-weight: 600; }
  .chip2 .x { cursor: pointer; color: #8a94a0; }
  .browser { width: 760px !important; }
  .browser .col { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
  .browser .chain { border: 1px solid #262c35; border-radius: 6px; padding: 6px 8px; margin-bottom: 6px; }
  .browser .chain.on { border-color: #1f6feb; }
  .vers { display: flex; gap: 3px; align-items: center; margin-top: 4px; font-size: 10px; }
  .vers span { border: 1px solid #2b323c; border-radius: 3px; padding: 0 4px; color: #8a94a0; }
  .vers span.h { border-color: #1f6feb; color: #fff; }
  .warn { color: #ffcc66; }
`;

const icon = (o: Obj) => (o.kind === "Annotations" ? "📐" : "🎨");
const who = (st: AnnStore, o: Obj) => (o.source === "ingested" ? "ingested" : o.author === st.me ? "you" : o.author);
const kinds: Kind[] = ["Annotations", "Segmentation"];

// ---------- shared: lock row, draft banner, conflict + retire + save dialogs, toast ----------
export function lockRow(st: AnnStore) {
  if (!st.blinded) return nothing;
  if (st.revealed) return html`<div class="lock">🔓 Blinding Reveal active for this participant (this session, audit-logged)</div>`;
  const n = st.hiddenCount();
  return html`<div class="lock">🔒 Blinded project — showing only your own work.${n ? html` ${n} other object${n > 1 ? "s" : ""} hidden.` : ""}
    ${st.canReveal() ? html`<br><button class="mini" @click=${(e: Event) => { e.stopPropagation(); if (confirm("Blinding Reveal: show everyone's Annotations and Segmentations for this participant until you close the viewer. This is audit-logged. Continue?")) st.reveal(); }}>Reveal for this participant…</button>` : ""}</div>`;
}

export function draftBanner(st: AnnStore, restore: () => void) {
  const ds = st.drafts().filter((d) => d.changes > 0);
  if (!ds.length) return nothing;
  return html`<div class="draft">⚠ Unsaved ${ds.map((d) => `${d.kind} on ${d.series}${d.basedOn ? ` (on top of ${d.basedOn})` : ""}`).join(", ")} from ${ds[0].at} were recovered.
    <button class="on mini" @click=${restore}>Restore</button><button class="mini" @click=${() => ds.forEach((d) => st.clearDraft(d.kind, d.series))}>Discard</button></div>`;
}

export function toast(st: AnnStore) { return st.toast ? html`<div class="toast">${st.toast}</div>` : nothing; }

export function conflictDialog(st: AnnStore) {
  const c = st.conflict;
  if (!c) return nothing;
  return html`<div class="C-overlay"><div class="C-box">
    <h4 style="margin:0 0 6px" class="warn">Someone saved a newer version first (409)</h4>
    <div class="B-cal"><b>${c.theirs.author}</b> saved <b>v${c.theirs.version}</b> of “${c.theirs.summary}” on ${c.theirs.created}, after you opened v${c.theirs.version - 1}.</div>
    <div class="B-cal">Your unsaved edits: ${c.mine}</div>
    <p style="display:flex;gap:6px;flex-wrap:wrap;justify-content:flex-end">
      <button @click=${() => st.resolve("theirs")}>Discard mine, load theirs</button>
      <button @click=${() => st.resolve("new")}>Save mine as a separate object</button>
      ${st.canChange(c.theirs) ? html`<button class="on" @click=${() => st.resolve("mine")}>Save mine on top (v${c.theirs.version + 1})</button>` : ""}
    </p><div class="B-cal muted">Nothing is merged automatically. Your edits stay in the draft until you choose.</div></div></div>`;
}

export function saveTarget(st: AnnStore, kind: Kind, series: string) {
  const base = st.loadedHead(kind, series);
  return base ? { base, label: `Supersede v${base.version} → v${base.version + 1}` } : { base: undefined, label: "Save as new (v1)" };
}

function historyRows(st: AnnStore, o: Obj) {
  return html`<div class="ann-hist">${st.history(o.chain).map((h) => html`<div>v${h.version} · ${h.created} · ${who(st, h)}${h.retired ? " · retired" : ""}${st.isHead(h) ? " · head" : ""}</div>`)}</div>`;
}

function retireBtn(st: AnnStore, o: Obj) {
  if (!st.canChange(o)) return nothing;
  return html`<button class="mini" title="Retire (kept for audit, hidden from lists)" @click=${(e: Event) => { e.stopPropagation(); if (confirm(`Retire “${o.summary}”? It disappears from lists and counts, but is kept (no hard delete).`)) st.retire(o); }}>Retire</button>`;
}

// ---------- A: tree in the series list ----------
export function treeChildren(st: AnnStore, series: string, open: Set<string>, rerender: () => void) {
  const rows = st.heads(series);
  return html`${rows.map((o) => html`<div class="ann-row ${st.loaded.has(o.id) ? "on" : ""}" @click=${() => st.toggle(o.id)}
      title="Click: show/hide in viewer">
      <span class="k">${st.loaded.has(o.id) ? "☑" : "☐"}</span><span class="k">${icon(o)}</span>
      <span class="t">${o.summary}<br><small>v${o.version} · ${who(st, o)}</small></span>
      <button class="mini" @click=${(e: Event) => { e.stopPropagation(); open.has(o.chain) ? open.delete(o.chain) : open.add(o.chain); rerender(); }}>${o.version > 1 ? `v1–${o.version}` : "v1"}</button>
      ${retireBtn(st, o)}</div>${open.has(o.chain) ? historyRows(st, o) : nothing}`)}`;
}

// ---------- B: inspector tab ----------
export function resultsTab(st: AnnStore, series: string, filter: "all" | "mine", setFilter: (f: "all" | "mine") => void, open: Set<string>, rerender: () => void, onSave: (k: Kind) => void, dirty: Record<Kind, number>) {
  return html`${lockRow(st)}
    <div style="display:flex;gap:4px;margin:4px 0"><button class=${filter === "all" ? "on mini" : "mini"} @click=${() => setFilter("all")}>All</button><button class=${filter === "mine" ? "on mini" : "mini"} @click=${() => setFilter("mine")}>Mine</button>
      <span class="muted" style="margin-left:auto;font-size:10px">on ${series}</span></div>
    ${kinds.map((k) => {
      const rows = st.heads(series).filter((o) => o.kind === k && (filter === "all" || o.author === st.me));
      const t = saveTarget(st, k, series);
      return html`<h5>${k} (${rows.length})</h5>
        <table class="res">${rows.map((o) => html`<tr class=${st.loaded.has(o.id) ? "on" : ""}>
          <td><input type="checkbox" .checked=${st.loaded.has(o.id)} @change=${() => st.toggle(o.id)}></td>
          <td>${o.summary}<br><small class="muted">${who(st, o)} · ${o.created}</small>${open.has(o.chain) ? historyRows(st, o) : nothing}</td>
          <td style="white-space:nowrap;text-align:right"><button class="mini" @click=${() => { open.has(o.chain) ? open.delete(o.chain) : open.add(o.chain); rerender(); }}>v${o.version}</button><br>${retireBtn(st, o)}</td></tr>`)}
          ${rows.length ? nothing : html`<tr><td class="muted" colspan="3">none</td></tr>`}</table>
        ${st.canAuthor() ? html`<p style="margin:4px 0;text-align:right"><button class=${dirty[k] ? "on mini" : "mini"} ?disabled=${!dirty[k]} @click=${() => onSave(k)}>💾 ${t.label}${dirty[k] ? " ●" : ""}</button></p>` : nothing}`;
    })}`;
}

// ---------- C: chips + open dialog ----------
export function chips(st: AnnStore, openBrowser: () => void) {
  const loaded = [...st.loaded].map((id) => st.objs.find((o) => o.id === id)!).filter(Boolean);
  return html`<div class="chips">${loaded.map((o) => html`<span class="chip2">${icon(o)} <b>${o.summary}</b> <span class="muted">v${o.version} · ${who(st, o)}</span>
      <span class="x" title="Hide" @click=${() => st.toggle(o.id)}>✕</span></span>`)}
    <span class="chip2 add" @click=${openBrowser}>＋ Annotations & Segmentations…</span></div>`;
}

export function browserDialog(st: AnnStore, series: string[], close: () => void) {
  return html`<div class="C-overlay" @click=${close}><div class="C-box browser" @click=${(e: Event) => e.stopPropagation()}>
    <h4 style="margin:0 0 6px">Annotations & Segmentations for this participant</h4>${lockRow(st)}
    ${series.map((s) => html`<h5>${s}</h5><div class="col">${kinds.map((k) => html`<div><div class="muted" style="margin-bottom:4px">${k}</div>
      ${st.heads(s).filter((o) => o.kind === k).map((o) => html`<div class="chain ${st.loaded.has(o.id) ? "on" : ""}">
        <div style="display:flex;gap:6px;align-items:center"><span>${icon(o)}</span><b style="flex:1">${o.summary}</b>
          <button class=${st.loaded.has(o.id) ? "on mini" : "mini"} @click=${() => st.toggle(o.id)}>${st.loaded.has(o.id) ? "Shown" : "Show"}</button>${retireBtn(st, o)}</div>
        <div class="muted" style="font-size:10px">${who(st, o)} · ${o.created}</div>
        <div class="vers">${st.history(o.chain).slice().reverse().map((h) => html`<span class=${st.isHead(h) ? "h" : ""} title="${h.created} · ${who(st, h)}">v${h.version}</span>${st.isHead(h) ? "" : "→"}`)}</div></div>`)}
      ${st.heads(s).some((o) => o.kind === k) ? nothing : html`<div class="muted">none</div>`}</div>`)}</div>`)}
    <p style="text-align:right"><button @click=${close}>Done</button></p></div></div>`;
}
