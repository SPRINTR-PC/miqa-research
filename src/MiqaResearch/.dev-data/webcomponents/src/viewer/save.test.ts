import { afterEach, describe, expect, it, vi } from "vitest";

import { SaveController, type ObjectKind, type ObjectVersion, type SaveHost } from "./save.ts";

const version = (v: number, extra: Partial<ObjectVersion> = {}): ObjectVersion => ({
  id: `id-${v}`,
  chain_id: "chain-1",
  kind: "annotation",
  version: v,
  author: "anna",
  created_at: "2026-10-08T10:00:00Z",
  series_instance_uid: `2.25.sr${v}`,
  ...extra,
});

class FakeHost implements SaveHost {
  apiRoot = "/api/v1/viewer";
  revisions: Record<ObjectKind, number> = { annotation: 0, segmentation: 0 };
  empty: Record<ObjectKind, boolean> = { annotation: false, segmentation: false };
  loaded: { kind: ObjectKind; head: ObjectVersion }[] = [];
  toasts: string[] = [];
  changes = 0;
  revision = (kind: ObjectKind) => this.revisions[kind];
  isEmpty = (kind: ObjectKind) => this.empty[kind];
  sourceSeries = () => ["2.25.base"];
  build = vi.fn(async (kind: ObjectKind) => new Blob([kind]));
  loadTheirs = vi.fn(async (kind: ObjectKind, head: ObjectVersion) => {
    this.loaded.push({ kind, head });
    this.revisions[kind] += 1; // clearing + loading fires annotation events
  });
  changed = () => void (this.changes += 1);
  toast = (message: string) => void this.toasts.push(message);
}

/** fetch double answering the save endpoint with queued responses; records the posted forms. */
function server(...responses: [number, unknown][]) {
  const posts: { url: string; form: FormData; headers: Record<string, string> }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init: RequestInit) => {
      posts.push({ url, form: init.body as FormData, headers: init.headers as Record<string, string> });
      const [status, body] = responses.shift()!;
      return new Response(JSON.stringify(body), { status });
    }),
  );
  return posts;
}

afterEach(() => vi.unstubAllGlobals());

describe("SaveController", () => {
  it("is enabled only when there are edits", () => {
    const host = new FakeHost();
    const save = new SaveController(host);
    expect(save.enabled("annotation")).toBe(false);

    host.revisions.annotation = 3;
    expect(save.enabled("annotation")).toBe(true);
    expect(save.enabled("segmentation")).toBe(false);

    host.empty.annotation = true; // drawn, then all deleted: nothing to save
    expect(save.enabled("annotation")).toBe(false);
  });

  it("saves as new (v1), then supersedes the version it saved", async () => {
    const host = new FakeHost();
    const save = new SaveController(host);
    document.cookie = "csrftoken=tok";
    const posts = server([201, version(1)], [201, version(2)]);
    host.revisions.annotation = 1;
    expect(save.label("annotation")).toBe("Save as new (v1)");

    await save.save("annotation");

    expect(posts[0].url).toBe("/api/v1/viewer/objects");
    expect(posts[0].headers["X-CSRFToken"]).toBe("tok");
    expect(posts[0].form.getAll("source_series")).toEqual(["2.25.base"]);
    expect(posts[0].form.get("supersedes")).toBeNull();
    expect(posts[0].form.get("file")).toBeInstanceOf(Blob);
    expect(save.enabled("annotation")).toBe(false);
    expect(save.label("annotation")).toBe("Supersede v1 → v2");
    expect(host.toasts).toEqual(["Annotations saved (v1)"]);

    host.revisions.annotation = 2;
    await save.save("annotation");
    expect(posts[1].form.get("supersedes")).toBe("id-1");
    expect(save.label("annotation")).toBe("Supersede v2 → v3");
  });

  it("supersedes a loaded head only when the user may change it", () => {
    const save = new SaveController(new FakeHost());
    save.setHead("annotation", version(4), false);
    expect(save.label("annotation")).toBe("Save as new (v1)");
    save.setHead("annotation", version(4), true);
    expect(save.label("annotation")).toBe("Supersede v4 → v5");
  });

  it("starts over when another base series is shown", () => {
    const host = new FakeHost();
    const save = new SaveController(host);
    save.setHead("annotation", version(2), true);
    host.revisions.annotation = 4;
    save.reset();
    expect(save.enabled("annotation")).toBe(false);
    expect(save.label("annotation")).toBe("Save as new (v1)");
  });

  it("never saves an empty object, even on top of a head (that one is retired instead)", () => {
    const host = new FakeHost();
    const save = new SaveController(host);
    save.setHead("annotation", version(1), true);
    host.empty.annotation = true;
    host.revisions.annotation = 1;
    expect(save.enabled("annotation")).toBe(false);
  });

  describe("a stale head (409)", () => {
    async function conflicted(canChange: boolean) {
      const host = new FakeHost();
      const save = new SaveController(host);
      save.setHead("annotation", version(1), true);
      host.revisions.annotation = 1;
      const theirs = version(2, { author: "bertil", created_at: "2026-10-08T11:30:00Z" });
      const posts = server([409, { detail: "a newer version was saved first", head: theirs, can_change: canChange }], [201, version(3)]);
      await save.save("annotation");
      return { host, save, posts, theirs };
    }

    it("opens the conflict naming who saved which version", async () => {
      const { save, theirs, host } = await conflicted(true);
      expect(save.conflict).toEqual({ kind: "annotation", head: theirs, canChange: true });
      expect(save.enabled("annotation")).toBe(true); // edits stay until the user chooses
      expect(host.toasts).toEqual([]);
    });

    it("Discard mine, load theirs", async () => {
      const { save, host, theirs } = await conflicted(false);
      await save.resolve("load-theirs");
      expect(host.loaded).toEqual([{ kind: "annotation", head: theirs }]);
      expect(save.conflict).toBeUndefined();
      expect(save.enabled("annotation")).toBe(false);
      expect(save.label("annotation")).toBe("Save as new (v1)"); // theirs, not ours to change
    });

    it("Save mine as a separate object", async () => {
      const { save, posts } = await conflicted(false);
      await save.resolve("separate");
      expect(posts[1].form.get("supersedes")).toBeNull();
      expect(save.conflict).toBeUndefined();
      expect(save.label("annotation")).toBe("Supersede v3 → v4");
    });

    it("Save mine on top, only if allowed", async () => {
      const { save, posts } = await conflicted(true);
      await save.resolve("on-top");
      expect(posts[1].form.get("supersedes")).toBe("id-2");
      expect(save.conflict).toBeUndefined();

      const denied = await conflicted(false);
      await denied.save.resolve("on-top");
      expect(denied.posts).toHaveLength(1);
      expect(denied.save.conflict).toBeDefined();
    });
  });

  it("shows other refusals as an error and keeps the edits", async () => {
    const host = new FakeHost();
    const save = new SaveController(host);
    server([403, { detail: "your roles don't allow saving" }]);
    host.revisions.segmentation = 1;
    await save.save("segmentation");
    expect(save.error).toBe("Couldn't save: your roles don't allow saving");
    expect(save.enabled("segmentation")).toBe(true);
  });

  it("saveAll saves every kind with edits", async () => {
    const host = new FakeHost();
    const save = new SaveController(host);
    const posts = server([201, version(1)], [201, version(1, { kind: "segmentation" })]);
    host.revisions.annotation = 1;
    host.revisions.segmentation = 1;
    await save.saveAll();
    expect(host.build.mock.calls.map(([k]) => k)).toEqual(["annotation", "segmentation"]);
    expect(posts).toHaveLength(2);
  });
});
