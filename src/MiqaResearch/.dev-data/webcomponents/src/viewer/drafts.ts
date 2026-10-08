// Drafts (#291, spec "Results UI"): unsaved edits autosaved as Cornerstone JSON (the adapter's
// snapshot) in IndexedDB, keyed per user × participant × series × kind, with the head they were based
// on. On the next viewer open a banner offers Restore / Discard; a draft is cleared on save or discard.
// 7-day TTL. Drafts survive logout (Clear-Site-Data stays "cache" only); another user never sees them.
import type { ObjectKind, ObjectVersion } from "./save.ts";

export const DRAFT_TTL_MS = 7 * 24 * 3600 * 1000;
/** Autosave this long after the last edit. */
export const AUTOSAVE_DELAY_MS = 500;

export interface DraftKey {
  /** The logged-in user's id. */
  user: string;
  participant: string;
  /** The base series the edits are on. */
  seriesUid: string;
  kind: ObjectKind;
}

/** The head the edits were made on top of, and whether the user may supersede it. */
export interface DraftBase {
  head: ObjectVersion;
  canChange: boolean;
}

export interface Draft extends DraftKey {
  key: string;
  base?: DraftBase;
  /** Epoch ms of the last autosave. */
  savedAt: number;
  /** Adapter snapshot (Cornerstone JSON); structured-cloneable. */
  data: unknown;
}

/** Where drafts live: IndexedDB in the browser, memory in unit tests. */
export interface DraftBackend {
  get(key: string): Promise<Draft | undefined>;
  put(draft: Draft): Promise<void>;
  delete(key: string): Promise<void>;
  all(): Promise<Draft[]>;
}

export function draftKey({ user, participant, seriesUid, kind }: DraftKey): string {
  return JSON.stringify([user, participant, seriesUid, kind]);
}

export class DraftStore {
  private readonly backend: DraftBackend;
  private readonly now: () => number;

  constructor(backend: DraftBackend, now: () => number = Date.now) {
    this.backend = backend;
    this.now = now;
  }

  private expired(draft: Draft): boolean {
    return this.now() - draft.savedAt >= DRAFT_TTL_MS;
  }

  /** The draft of `key`; an expired one is deleted instead. */
  async load(key: DraftKey): Promise<Draft | undefined> {
    const k = draftKey(key);
    const draft = await this.backend.get(k);
    if (!draft || draft.user !== key.user) return undefined;
    if (this.expired(draft)) {
      await this.backend.delete(k);
      return undefined;
    }
    return draft;
  }

  async save(key: DraftKey, base: DraftBase | undefined, data: unknown): Promise<void> {
    const { user, participant, seriesUid, kind } = key;
    await this.backend.put({ key: draftKey(key), user, participant, seriesUid, kind, base, savedAt: this.now(), data });
  }

  async discard(key: DraftKey): Promise<void> {
    await this.backend.delete(draftKey(key));
  }

  /** Delete every expired draft (any user's: they can't be restored any more). */
  async purgeExpired(): Promise<void> {
    for (const draft of await this.backend.all()) if (this.expired(draft)) await this.backend.delete(draft.key);
  }
}

export function memoryDraftBackend(): DraftBackend {
  const drafts = new Map<string, Draft>();
  return {
    get: async (key) => structuredClone(drafts.get(key)),
    put: async (draft) => void drafts.set(draft.key, structuredClone(draft)),
    delete: async (key) => void drafts.delete(key),
    all: async () => [...drafts.values()].map((d) => structuredClone(d)),
  };
}

const DB = "mires-viewer-drafts";
const STORE = "drafts";

/** Drafts in IndexedDB (one object store, keyed by `draftKey`). */
export function indexedDbDraftBackend(factory: IDBFactory = indexedDB): DraftBackend {
  let db: Promise<IDBDatabase> | undefined;
  const open = () =>
    (db ??= new Promise((resolve, reject) => {
      const request = factory.open(DB, 1);
      request.onupgradeneeded = () => request.result.createObjectStore(STORE, { keyPath: "key" });
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    }));
  const run = async <T>(mode: IDBTransactionMode, op: (store: IDBObjectStore) => IDBRequest): Promise<T> => {
    const tx = (await open()).transaction(STORE, mode);
    const request = op(tx.objectStore(STORE));
    return new Promise((resolve, reject) => {
      tx.oncomplete = () => resolve(request.result as T);
      tx.onerror = tx.onabort = () => reject(tx.error ?? request.error);
    });
  };
  return {
    get: (key) => run("readonly", (s) => s.get(key)),
    put: (draft) => run("readwrite", (s) => s.put(draft)),
    delete: (key) => run("readwrite", (s) => s.delete(key)),
    all: () => run("readonly", (s) => s.getAll()),
  };
}

/** IndexedDB when the browser has it, else memory (drafts then last only as long as the page). */
export function defaultDraftBackend(): DraftBackend {
  return typeof indexedDB === "undefined" ? memoryDraftBackend() : indexedDbDraftBackend();
}

const KINDS = ["annotation", "segmentation"] as const;

/** What the draft controller needs of the viewer (the element). */
export interface DraftHost {
  /** The draft key of `kind` now; undefined when drafts are off (no user / participant, view-only). */
  key(kind: ObjectKind): DraftKey | undefined;
  /** Bumps on every edit of `kind`. */
  revision(kind: ObjectKind): number;
  /** Unsaved edits of `kind` (Save's dirty). */
  dirty(kind: ObjectKind): boolean;
  isEmpty(kind: ObjectKind): boolean;
  /** The head `kind` is edited on top of. */
  base(kind: ObjectKind): DraftBase | undefined;
  /** Cornerstone JSON of `kind` (the adapter's snapshot). */
  snapshot(kind: ObjectKind): Promise<unknown>;
  /** Show the draft's edits (on top of its base head). */
  restore(draft: Draft): Promise<void>;
  /** State changed: re-render. */
  changed(): void;
}

/**
 * Autosave and recovery. `check()` on open (and on another base series) finds the drafts to offer;
 * `edited()` after every change debounces a write of each kind with unsaved edits; `saved(kind)` clears
 * it. A kind whose draft is offered isn't autosaved until the user restores or discards it.
 */
export class DraftController {
  /** Drafts offered in the banner. */
  pending: Draft[] = [];
  error = "";
  private readonly store: DraftStore;
  private readonly host: DraftHost;
  private readonly delay: number;
  private readonly seen: Record<ObjectKind, number> = { annotation: -1, segmentation: -1 };
  private readonly timers: Partial<Record<ObjectKind, ReturnType<typeof setTimeout>>> = {};
  /** Store operations, in order (a write never lands after the discard that follows it). */
  private queue: Promise<unknown> = Promise.resolve();
  private checking = false;

  constructor(store: DraftStore, host: DraftHost, delay = AUTOSAVE_DELAY_MS) {
    this.store = store;
    this.host = host;
    this.delay = delay;
  }

  private enqueue(op: () => Promise<unknown>): Promise<unknown> {
    this.queue = this.queue.then(op).catch((e) => console.warn("Draft storage failed", e));
    return this.queue;
  }

  /** Offer the drafts of the base series shown (expired ones are purged first). */
  async check(): Promise<void> {
    this.cancelTimers();
    this.pending = [];
    this.checking = true;
    const found: Draft[] = [];
    await this.enqueue(async () => {
      await this.store.purgeExpired();
      for (const kind of KINDS) {
        const key = this.host.key(kind);
        const draft = key && (await this.store.load(key));
        if (draft) found.push(draft);
      }
    });
    this.pending = found;
    this.checking = false;
    this.host.changed();
    this.edited(); // edits made while checking
  }

  private isPending(kind: ObjectKind): boolean {
    return this.pending.some((d) => d.kind === kind);
  }

  /** Something changed: autosave each kind with new edits, debounced. */
  edited(): void {
    if (this.checking) return;
    for (const kind of KINDS) {
      const revision = this.host.revision(kind);
      if (revision === this.seen[kind] || this.isPending(kind) || !this.host.key(kind)) continue;
      const first = this.seen[kind] === -1 && !this.host.dirty(kind);
      this.seen[kind] = revision;
      if (first) continue; // nothing edited yet
      clearTimeout(this.timers[kind]);
      this.timers[kind] = setTimeout(() => void this.enqueue(() => this.write(kind)), this.delay);
    }
  }

  private async write(kind: ObjectKind): Promise<void> {
    const key = this.host.key(kind);
    if (!key || this.isPending(kind)) return;
    if (this.host.dirty(kind) && !this.host.isEmpty(kind)) {
      await this.store.save(key, this.host.base(kind), await this.host.snapshot(kind));
    } else await this.store.discard(key);
  }

  /** Saved (or replaced by the head saved first): its draft goes. */
  saved(kind: ObjectKind): void {
    clearTimeout(this.timers[kind]);
    this.seen[kind] = this.host.revision(kind);
    const key = this.host.key(kind);
    if (key) void this.enqueue(() => this.store.discard(key));
  }

  async restore(kind: ObjectKind): Promise<void> {
    const draft = this.pending.find((d) => d.kind === kind);
    if (!draft) return;
    this.pending = this.pending.filter((d) => d !== draft);
    this.error = "";
    try {
      await this.host.restore(draft);
    } catch (e) {
      this.error = `Couldn't restore the draft: ${e instanceof Error ? e.message : String(e)}`;
    }
    this.seen[kind] = this.host.revision(kind) - 1; // autosave what was restored, as this page's draft
    this.edited();
    this.host.changed();
  }

  async discard(kind: ObjectKind): Promise<void> {
    const draft = this.pending.find((d) => d.kind === kind);
    if (!draft) return;
    this.pending = this.pending.filter((d) => d !== draft);
    this.seen[kind] = -1;
    const done = this.enqueue(() => this.store.discard(draft));
    this.edited(); // edits made meanwhile are autosaved now
    this.host.changed();
    await done;
  }

  private cancelTimers(): void {
    for (const kind of KINDS) clearTimeout(this.timers[kind]);
  }

  dispose(): void {
    this.cancelTimers();
  }
}
