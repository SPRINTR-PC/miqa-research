// Results tree (#290, spec "Results UI"): the participant's Annotations and Segmentations (chain heads from
// the object API), nested under their base series in the series list. Click shows / hides a head (the host
// brings its source series in and imports the SR / SEG), chips list what's shown, ⋯ opens History and Retire,
// "Show retired" lists retired chains read-only, and on Blinded Annotation projects the lock row offers the
// Blinding Reveal. No CS3D; the server decides what's listed and who may retire or reveal.
import { csrfToken } from "./first-render.ts";
import type { ObjectKind, ObjectVersion } from "./save.ts";
import { viewerHeaders } from "./viewer-session.ts";

/** A version from the object API (its VersionOut). */
export interface ResultVersion extends ObjectVersion {
  source: string;
  series_description: string | null;
  modality: string | null;
  retired: boolean;
  source_series_uids: string[];
  /** The series it's drawn on: the Fusion base. */
  base_series_uid: string | null;
}

/** A chain from the object API (its ChainOut): the head's fields, its history (oldest first), the caller's rights. */
export interface ResultChain extends ResultVersion {
  can_change: boolean;
  history: ResultVersion[];
}

/** Blinded Annotation state of the participant for this user and login session (#288). */
export interface BlindingStatus {
  blinded: boolean;
  revealed: boolean;
  can_reveal: boolean;
  hidden: number;
}

export const NOUN: Record<ObjectKind, string> = { annotation: "Annotations", segmentation: "Segmentation" };

export const kindOf = (chain: ResultVersion): ObjectKind => (chain.kind === "segmentation" ? "segmentation" : "annotation");

/** The series a chain is listed under. */
export const baseOf = (chain: ResultVersion): string => chain.base_series_uid ?? chain.source_series_uids[0] ?? "";

/**
 * Whether the viewer can show it: an SR or a SEG, not retired. Bulk ANN shows on its slide anyway (#292);
 * RTSTRUCT isn't read.
 */
export function showable(chain: ResultChain): boolean {
  return !chain.retired && (chain.modality === "SR" || chain.modality === "SEG");
}

export interface ResultsHost {
  /** Viewer API root, e.g. `/api/v1/viewer`. */
  readonly apiRoot: string;
  /** Study Participant id; nothing is listed without it. */
  readonly participant: string;
  /** Bring the chain's source series in (replace / fuse, size guard) and show its head. Throws when it can't. */
  show(chain: ResultChain): Promise<void>;
  /** Take the chain's head out of the views. */
  hide(chain: ResultChain): void;
  changed(): void;
  toast(message: string): void;
}

/** An action waiting for its confirm. */
export type Pending = { action: "retire"; chain: ResultChain } | { action: "reveal" };

export class ResultsController {
  chains: ResultChain[] = [];
  blinding: BlindingStatus | undefined;
  /** The first listing came back. */
  loaded = false;
  showRetired = false;
  /** Chains shown in the views, by chain id. */
  readonly shown = new Map<string, ResultChain>();
  /** Chain id being shown, or the action being run. */
  busy: string | undefined;
  /** Chain id whose ⋯ menu is open. */
  menu: string | undefined;
  /** Chain id whose History is open. */
  history: string | undefined;
  pending: Pending | undefined;
  error = "";
  private readonly host: ResultsHost;

  constructor(host: ResultsHost) {
    this.host = host;
  }

  private get participantUrl(): string {
    return `${this.host.apiRoot}/participants/${encodeURIComponent(this.host.participant)}`;
  }

  /** List the chains (and retired ones when asked) and the blinding state again. */
  async refresh(): Promise<void> {
    if (!this.host.participant) return;
    const query = new URLSearchParams({ participant: this.host.participant });
    if (this.showRetired) query.set("include_retired", "true");
    try {
      const [chains, blinding] = await Promise.all([
        getJson<ResultChain[]>(`${this.host.apiRoot}/objects?${query}`),
        getJson<BlindingStatus>(`${this.participantUrl}/blinding`),
      ]);
      // Keep only what looks like chains (a mis-routed or stubbed response lists nothing rather than breaking the list).
      this.chains = Array.isArray(chains) ? chains.filter((c) => Array.isArray(c?.source_series_uids) && Array.isArray(c.history)) : [];
      this.blinding = typeof blinding?.blinded === "boolean" ? blinding : undefined;
      // A head shown before stays shown as the listed (possibly newer) chain.
      for (const [id] of this.shown) {
        const now = chains.find((c) => c.chain_id === id);
        if (now && !now.retired) this.shown.set(id, now);
      }
      this.error = "";
    } catch (e) {
      this.error = `Couldn't list the results: ${message(e)}`;
    } finally {
      this.loaded = true;
      this.host.changed();
    }
  }

  /** Chains listed under `seriesUid` (their base series), newest first as the server orders them. */
  rows(seriesUid: string): ResultChain[] {
    return this.chains.filter((c) => baseOf(c) === seriesUid);
  }

  /** Show a head (the host brings its source series in), or hide it if shown. */
  async toggle(chain: ResultChain): Promise<void> {
    if (this.busy) return;
    if (this.shown.has(chain.chain_id)) return this.hide(chain.chain_id);
    if (!showable(chain)) return;
    this.busy = chain.chain_id;
    this.error = "";
    this.host.changed();
    try {
      await this.host.show(chain);
      this.shown.set(chain.chain_id, chain);
    } catch (e) {
      if (!(e instanceof Quiet)) this.error = `Couldn't show ${NOUN[kindOf(chain)]} v${chain.version}: ${message(e)}`;
    } finally {
      this.busy = undefined;
      this.host.changed();
    }
  }

  hide(chainId: string): void {
    const chain = this.shown.get(chainId);
    if (!chain) return;
    this.shown.delete(chainId);
    this.host.hide(chain);
    this.host.changed();
  }

  /** Hide every shown head that `drop` matches (e.g. after another base series replaced the shown one). */
  hideWhere(drop: (chain: ResultChain) => boolean): void {
    for (const chain of [...this.shown.values()]) if (drop(chain)) this.hide(chain.chain_id);
  }

  /** Mark a head as shown that the host showed itself (409 "load theirs"). */
  markShown(chain: ResultChain): void {
    this.shown.set(chain.chain_id, chain);
    this.host.changed();
  }

  /** The listed chain with this id. */
  chain(chainId: string): ResultChain | undefined {
    return this.chains.find((c) => c.chain_id === chainId);
  }

  openMenu(chainId: string): void {
    this.menu = this.menu === chainId ? undefined : chainId;
    this.host.changed();
  }

  openHistory(chainId: string): void {
    this.menu = undefined;
    this.history = this.history === chainId ? undefined : chainId;
    this.host.changed();
  }

  ask(pending: Pending): void {
    this.menu = undefined;
    this.pending = pending;
    this.host.changed();
  }

  cancel(): void {
    this.pending = undefined;
    this.host.changed();
  }

  async setShowRetired(on: boolean): Promise<void> {
    this.showRetired = on;
    await this.refresh();
  }

  /** Run the confirmed action: Retire (the head; hidden if shown) or the Blinding Reveal. */
  async confirm(): Promise<void> {
    const pending = this.pending;
    if (!pending || this.busy) return;
    this.busy = pending.action;
    this.host.changed();
    try {
      if (pending.action === "retire") {
        const { chain } = pending;
        const { status, body } = await postJson<{ detail?: string }>(`${this.host.apiRoot}/objects/${chain.id}/retire`);
        if (status === 200) {
          this.hide(chain.chain_id);
          this.host.toast(`${summary(chain)} retired`);
        } else if (status === 409) this.error = "A newer version was saved: listing it now. Retire that one if you still want to.";
        else this.error = `Couldn't retire: ${body.detail ?? `HTTP ${status}`}`;
      } else {
        const { status, body } = await postJson<{ detail?: string }>(`${this.participantUrl}/blinding-reveal`);
        if (status === 200) this.host.toast("Blinding Reveal active for this participant");
        else this.error = `Couldn't reveal: ${body.detail ?? `HTTP ${status}`}`;
      }
    } catch (e) {
      this.error = message(e);
    } finally {
      this.pending = undefined;
      this.busy = undefined;
    }
    await this.refresh();
  }
}

/** Thrown by the host when it already told the user why (a refusal over the view). */
export class Quiet extends Error {}

const summary = (chain: ResultVersion) => `${NOUN[kindOf(chain)]} v${chain.version}`;

async function getJson<T>(url: string): Promise<T> {
  const response = await fetch(url, { credentials: "same-origin", headers: viewerHeaders({ Accept: "application/json" }) });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return (await response.json()) as T;
}

export async function postJson<T>(url: string): Promise<{ status: number; body: T }> {
  const response = await fetch(url, { method: "POST", credentials: "same-origin", headers: viewerHeaders({ "X-CSRFToken": csrfToken() }) });
  return { status: response.status, body: (await response.json().catch(() => ({}))) as T };
}

export function message(e: unknown): string {
  return e instanceof Error ? e.message : String(e);
}
