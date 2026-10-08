// Save (#289, spec "Results UI"): one Save per kind (Annotations as SR, the Segmentation as SEG),
// enabled when there are edits; "Supersede vN → vN+1" on top of a head the user may change, else
// "Save as new (v1)". A stale head (409) opens the conflict: discard mine and load theirs, save mine as
// a separate object, or save mine on top (only if allowed). No merge; edits stay until the user chooses.
// No CS3D: the host (the element) builds the bytes through the adapter and loads heads.
import { csrfToken } from "./first-render.ts";

export type ObjectKind = "annotation" | "segmentation";
export const OBJECT_KINDS: readonly ObjectKind[] = ["annotation", "segmentation"];

/** A version from the object API (subset of its VersionOut). */
export interface ObjectVersion {
  id: string;
  chain_id: string;
  kind: string;
  version: number;
  author: string | null;
  created_at: string;
  series_instance_uid: string;
}

export interface Conflict {
  kind: ObjectKind;
  /** The chain's current head, saved by someone else first. */
  head: ObjectVersion;
  /** May the user supersede it ("Save mine on top"). */
  canChange: boolean;
}

export type ConflictChoice = "load-theirs" | "separate" | "on-top";

export interface SaveHost {
  /** Viewer API root, e.g. `/api/v1/viewer`. */
  apiRoot: string;
  /** Bumps on every edit of that kind. */
  revision(kind: ObjectKind): number;
  /** Nothing drawn or painted of that kind. */
  isEmpty(kind: ObjectKind): boolean;
  /** Series Instance UIDs the object is made on, base series first. */
  sourceSeries(kind: ObjectKind): string[];
  /** The SR / SEG as DICOM Part 10 bytes. */
  build(kind: ObjectKind): Promise<Blob>;
  /** Drop the local edits of `kind` and show `head` instead. */
  loadTheirs(kind: ObjectKind, head: ObjectVersion): Promise<void>;
  /** State changed: re-render. */
  changed(): void;
  toast(message: string): void;
}

const NOUN: Record<ObjectKind, string> = { annotation: "Annotations", segmentation: "Segmentation" };

export class SaveController {
  /** The head each kind is edited on top of, and whether the user may supersede it. */
  private readonly heads: Partial<Record<ObjectKind, { version: ObjectVersion; canChange: boolean }>> = {};
  /** Revision of each kind at the last save or load: edits are revisions past it. */
  private readonly baseline: Record<ObjectKind, number> = { annotation: 0, segmentation: 0 };
  saving: ObjectKind | undefined;
  conflict: Conflict | undefined;
  error = "";
  private readonly host: SaveHost;

  constructor(host: SaveHost) {
    this.host = host;
  }

  /** Edit on top of `head` (a loaded or just-saved version). */
  setHead(kind: ObjectKind, head: ObjectVersion, canChange: boolean): void {
    this.heads[kind] = { version: head, canChange };
    this.baseline[kind] = this.host.revision(kind);
    this.host.changed();
  }

  /** Another base series is shown (#284 replace): nothing loaded, no edits counted so far. */
  reset(): void {
    for (const kind of OBJECT_KINDS) {
      delete this.heads[kind];
      this.baseline[kind] = this.host.revision(kind);
    }
    this.conflict = undefined;
    this.error = "";
    this.host.changed();
  }

  head(kind: ObjectKind): ObjectVersion | undefined {
    return this.heads[kind]?.version;
  }

  dirty(kind: ObjectKind): boolean {
    return this.host.revision(kind) !== this.baseline[kind];
  }

  /** Edits to save. Never an empty SR / SEG: an object nobody wants any more is retired (#290). */
  enabled(kind: ObjectKind): boolean {
    return this.dirty(kind) && !this.saving && !this.host.isEmpty(kind);
  }

  private supersedable(kind: ObjectKind): ObjectVersion | undefined {
    const head = this.heads[kind];
    return head?.canChange ? head.version : undefined;
  }

  label(kind: ObjectKind): string {
    const head = this.supersedable(kind);
    return head ? `Supersede v${head.version} → v${head.version + 1}` : "Save as new (v1)";
  }

  /** Save `kind`: supersedes the head the user may change, else a new object. */
  async save(kind: ObjectKind): Promise<void> {
    if (!this.enabled(kind)) return;
    await this.post(kind, this.supersedable(kind)?.id);
  }

  /** Ctrl/⌘+S: every kind with edits, in turn; stops at a conflict. */
  async saveAll(): Promise<void> {
    for (const kind of OBJECT_KINDS) {
      if (this.conflict) return;
      await this.save(kind);
    }
  }

  async resolve(choice: ConflictChoice): Promise<void> {
    const conflict = this.conflict;
    if (!conflict || this.saving) return;
    if (choice === "on-top" && !conflict.canChange) return;
    if (choice === "load-theirs") {
      this.conflict = undefined;
      try {
        await this.host.loadTheirs(conflict.kind, conflict.head);
      } catch (e) {
        this.error = `Couldn't load v${conflict.head.version}: ${e instanceof Error ? e.message : String(e)}`;
      }
      this.setHead(conflict.kind, conflict.head, conflict.canChange);
      return;
    }
    await this.post(conflict.kind, choice === "on-top" ? conflict.head.id : undefined);
  }

  /** Close the conflict without choosing (edits stay). */
  dismiss(): void {
    this.conflict = undefined;
    this.error = "";
    this.host.changed();
  }

  private async post(kind: ObjectKind, supersedes: string | undefined): Promise<void> {
    this.saving = kind;
    this.error = "";
    this.host.changed();
    try {
      const revision = this.host.revision(kind);
      const form = new FormData();
      form.append("file", await this.host.build(kind), `${kind}.dcm`);
      this.host.sourceSeries(kind).forEach((uid) => form.append("source_series", uid));
      if (supersedes) form.append("supersedes", supersedes);
      const response = await fetch(`${this.host.apiRoot}/objects`, {
        method: "POST",
        body: form,
        credentials: "same-origin",
        headers: { "X-CSRFToken": csrfToken() },
      });
      const body = await response.json().catch(() => ({}));
      if (response.status === 201) {
        this.conflict = undefined;
        this.heads[kind] = { version: body as ObjectVersion, canChange: true }; // the author may change their own
        this.baseline[kind] = revision;
        this.host.toast(`${NOUN[kind]} saved (v${body.version})`);
      } else if (response.status === 409) {
        this.conflict = { kind, head: body.head, canChange: !!body.can_change };
      } else {
        this.error = `Couldn't save: ${body.detail ?? response.statusText}`;
      }
    } catch (e) {
      this.error = `Couldn't save: ${e instanceof Error ? e.message : String(e)}`;
    } finally {
      this.saving = undefined;
      this.host.changed();
    }
  }
}
