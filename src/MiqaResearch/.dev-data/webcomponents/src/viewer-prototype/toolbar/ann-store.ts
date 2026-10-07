// PROTOTYPE — throwaway. Ticket #202 (map #176): stub server for the Annotations /
// Segmentations UI. In memory, seeded per page load. Drafts go to localStorage under
// a PROTOTYPE key (stands in for IndexedDB) so "simulate crash" survives a reload.
// Rules from #189 (ADR 0026): immutable objects, one linear chain each, head = current,
// save on a stale head → 409, Retire instead of delete, Blinded Annotation + Blinding Reveal.

export type Kind = "Annotations" | "Segmentation";
export type Who = "annotator" | "pi" | "viewer";
export interface Obj {
  id: string; chain: string; version: number; kind: Kind; series: string;
  source: "viewer" | "ingested"; author?: string; created: string; summary: string; retired: boolean;
}
export interface Draft { kind: Kind; series: string; basedOn?: string; changes: number; at: string }

const ME: Record<Who, string> = { annotator: "A. Andersson (you)", pi: "C. Carlsson, PI (you)", viewer: "D. Dahl (you)" };
const DRAFT_KEY = "PROTOTYPE-wipe-me-viewer-drafts";

export class AnnStore {
  objs: Obj[] = [];
  loaded = new Set<string>(); // object ids shown in the viewer
  revealed = false;
  conflict?: { kind: Kind; series: string; mine: string; theirs: Obj };
  toast = "";
  onChange = () => {};
  private n = 0;

  who: Who;
  blinded: boolean;
  constructor(who: Who, blinded: boolean) {
    this.who = who;
    this.blinded = blinded;
    const me = ME[who];
    const add = (o: Partial<Obj> & { chain: string; kind: Kind; series: string; summary: string }, versions = 1, retired = false) => {
      for (let v = 1; v <= versions; v++) {
        this.objs.push({ id: `${o.chain}-v${v}`, version: v, source: "viewer", created: `2026-09-${10 + v + this.n++}`, retired: retired && v === versions, author: undefined, ...o } as Obj);
      }
    };
    add({ chain: "sr-mine", kind: "Annotations", series: "CT", author: me, summary: "3 Length, 1 EllipticalROI" }, 2);
    add({ chain: "sr-berg", kind: "Annotations", series: "CT", author: "B. Berg", summary: "5 Length, 2 Probe" }, 3);
    add({ chain: "sr-ingest", kind: "Annotations", series: "CT", source: "ingested", summary: "RECIST target lesions (ingested SR)" });
    add({ chain: "sr-old", kind: "Annotations", series: "CT", author: "B. Berg", summary: "1 Length (test)" }, 1, true);
    add({ chain: "seg-mine", kind: "Segmentation", series: "CT", author: me, summary: "Liver, Tumour 1" });
    add({ chain: "seg-berg", kind: "Segmentation", series: "PT", author: "B. Berg", summary: "Lesion SUV>2.5" }, 2);
  }

  get me() { return ME[this.who]; }
  canAuthor() { return this.who !== "viewer"; }
  canReveal() { return this.who === "pi"; }
  isHead(o: Obj) { return !this.objs.some((x) => x.chain === o.chain && x.version > o.version); }
  canChange(o: Obj) { return this.who === "pi" || (this.who === "annotator" && o.author === this.me); }
  /** Blinded projects: own work only (ingested hidden) unless a Blinding Reveal is active. */
  visible(o: Obj) { return !this.blinded || this.revealed || o.author === this.me; }
  heads(series?: string, opts: { retired?: boolean } = {}) {
    return this.objs.filter((o) => this.isHead(o) && (series ? o.series === series : true) && (opts.retired || !o.retired) && this.visible(o));
  }
  hiddenCount() { return this.objs.filter((o) => this.isHead(o) && !o.retired && !this.visible(o)).length; }
  history(chain: string) { return this.objs.filter((o) => o.chain === chain).sort((a, b) => b.version - a.version); }
  loadedHead(kind: Kind, series: string) {
    return [...this.loaded].map((id) => this.objs.find((o) => o.id === id)!).find((o) => o.kind === kind && o.series === series && o.author === this.me);
  }

  toggle(id: string) { this.loaded.has(id) ? this.loaded.delete(id) : this.loaded.add(id); this.onChange(); }
  reveal() { this.revealed = true; this.flash("Blinding Reveal for this participant — audit-logged, ends when the viewer closes."); }

  /** Save the edits on `series`. Edits on top of a loaded own (or PI-editable) object supersede it; otherwise a new chain. */
  save(kind: Kind, series: string, summary: string, basedOnId?: string) {
    const base = basedOnId ? this.objs.find((o) => o.id === basedOnId) : undefined;
    if (base && !this.isHead(base)) {
      const theirs = this.history(base.chain)[0];
      this.conflict = { kind, series, mine: summary, theirs };
      this.onChange();
      return "409";
    }
    const chain = base?.chain ?? `${kind === "Annotations" ? "sr" : "seg"}-new${this.n++}`;
    const version = base ? base.version + 1 : 1;
    const o: Obj = { id: `${chain}-v${version}`, chain, version, kind, series, source: "viewer", author: this.me, created: "2026-10-07", summary, retired: false };
    this.objs.push(o);
    if (base) this.loaded.delete(base.id);
    this.loaded.add(o.id);
    this.clearDraft(kind, series);
    this.flash(base ? `Saved ${kind} v${version} — supersedes v${base.version}` : `Saved new ${kind} (v1)`);
    return o;
  }
  /** 409 resolution: keep theirs (discard mine), or save mine on top of their head (explicit supersede). */
  resolve(choice: "theirs" | "mine" | "new") {
    const c = this.conflict!;
    this.conflict = undefined;
    if (choice === "theirs") { this.loaded.add(c.theirs.id); this.clearDraft(c.kind, c.series); this.flash(`Loaded ${c.theirs.author}'s v${c.theirs.version}; your edits discarded`); return; }
    if (choice === "new") { this.save(c.kind, c.series, c.mine); return; }
    this.save(c.kind, c.series, c.mine, c.theirs.id);
  }
  retire(o: Obj) {
    const head = this.history(o.chain)[0];
    head.retired = true;
    this.loaded.delete(head.id);
    this.flash(`Retired ${o.kind} “${o.summary}” — hidden from lists, kept for audit`);
  }
  /** Stand-in for another user superseding a chain while you have it open. */
  simulateOther(chain: string) {
    const h = this.history(chain)[0];
    this.objs.push({ ...h, id: `${chain}-v${h.version + 1}`, version: h.version + 1, author: h.author === this.me ? "B. Berg" : h.author, created: "2026-10-07", summary: h.summary + " (+1 edit)" });
    this.flash(`(simulated) someone else saved v${h.version + 1} of “${h.summary}”`);
  }

  // drafts: autosave of unsaved edits (Cornerstone JSON in IndexedDB in the real thing)
  drafts(): Draft[] { try { return JSON.parse(localStorage.getItem(DRAFT_KEY) ?? "[]"); } catch { return []; } }
  writeDraft(d: Draft) {
    const ds = this.drafts().filter((x) => !(x.kind === d.kind && x.series === d.series));
    try { localStorage.setItem(DRAFT_KEY, JSON.stringify([...ds, d])); } catch { /* prototype */ }
  }
  clearDraft(kind: Kind, series: string) {
    try { localStorage.setItem(DRAFT_KEY, JSON.stringify(this.drafts().filter((x) => !(x.kind === kind && x.series === series)))); } catch { /* prototype */ }
    this.onChange();
  }
  flash(s: string) { this.toast = s; this.onChange(); setTimeout(() => { if (this.toast === s) { this.toast = ""; this.onChange(); } }, 4000); }
}
