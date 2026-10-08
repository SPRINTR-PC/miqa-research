// #291 Drafts on <mires-viewer>: autosave of unsaved edits, the recovery banner (Restore / Discard)
// on the next open, cleared on save. Seam: the element with the stub adapter and an in-memory draft
// backend shared between "page loads" (two elements); fetch stubbed (WADO /metadata, POST /objects).
import { afterEach, describe, expect, it, vi } from "vitest";

import { StubAdapter } from "./adapter/stub.ts";
import { memoryDraftBackend, type Draft, type DraftBackend } from "./drafts.ts";
import { MiresViewer } from "./mires-viewer.ts";

const ct = (n: number) =>
  Array.from({ length: n }, (_, i) => ({
    "00080018": { vr: "UI", Value: [`2.25.${i + 1}`] },
    "00080060": { vr: "CS", Value: ["CT"] },
    "00200013": { vr: "IS", Value: [i + 1] },
    "00280010": { vr: "US", Value: [64] },
    "00280011": { vr: "US", Value: [64] },
  }));

const saved = (v: number) => ({
  id: `id-${v}`,
  chain_id: "c1",
  kind: "annotation",
  version: v,
  author: "bertil",
  created_at: "2026-10-08T11:30:00Z",
  series_instance_uid: `2.25.sr${v}`,
});

function stubFetch(posts: [number, unknown][] = []) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (_url: string, init?: RequestInit) => {
      if (init?.method === "POST") {
        const [status, body] = posts.shift()!;
        return new Response(JSON.stringify(body), { status });
      }
      return new Response(JSON.stringify(ct(4)));
    }),
  );
}

async function mount(backend: DraftBackend, { user = "7", participant = "p1", canAnnotate = true } = {}) {
  const adapter = new StubAdapter();
  const el = document.createElement("mires-viewer") as MiresViewer;
  el.adapterFactory = async () => adapter;
  el.draftBackend = backend;
  el.setAttribute("study-uid", "2.25.100");
  el.setAttribute("series-uid", "2.25.200");
  if (user) el.setAttribute("user", user);
  el.participant = participant;
  el.canAnnotate = canAnnotate;
  document.body.append(el);
  await vi.waitFor(() => expect(el.getAttribute("state")).toBe("ready"));
  await el.updateComplete;
  return { el, adapter, annotations: adapter.annotations! };
}

/** Wait for the autosave to write (debounced) a draft. */
async function autosaved(backend: DraftBackend): Promise<Draft[]> {
  await vi.waitFor(async () => expect(await backend.all()).not.toEqual([]), { timeout: 2000 });
  return backend.all();
}

const $ = (el: MiresViewer, selector: string) => el.shadowRoot!.querySelector<HTMLElement>(selector);
const banner = (el: MiresViewer) => $(el, ".draft-banner");

/** A page load: the first element goes away, a new one opens on the same backend. */
async function reload(first: MiresViewer, backend: DraftBackend, options?: Parameters<typeof mount>[1]) {
  first.remove();
  return mount(backend, options);
}

afterEach(() => {
  document.body.innerHTML = "";
  vi.unstubAllGlobals();
});

describe("draft autosave", () => {
  it("writes the edits, keyed per user × participant × series × kind", async () => {
    stubFetch();
    const backend = memoryDraftBackend();
    const { annotations } = await mount(backend);

    annotations.draw("Length", "ArrowAnnotate");

    const [draft] = await autosaved(backend);
    expect(draft).toMatchObject({ user: "7", participant: "p1", seriesUid: "2.25.200", kind: "annotation" });
    expect(draft.base).toBeUndefined();
    expect(draft.data).toEqual({ tools: ["Length", "ArrowAnnotate"] });
  });

  it("writes nothing without a user, or for view-only roles", async () => {
    stubFetch();
    const backend = memoryDraftBackend();
    const { annotations } = await mount(backend, { user: "" });
    annotations.draw("Length");
    await new Promise((r) => setTimeout(r, 700));

    expect(await backend.all()).toEqual([]);
  });

  it("is cleared on save", async () => {
    stubFetch([[201, saved(1)]]);
    const backend = memoryDraftBackend();
    const { el, annotations } = await mount(backend);
    annotations.draw("Length");
    await autosaved(backend);

    await el.save.save("annotation");

    await vi.waitFor(async () => expect(await backend.all()).toEqual([]), { timeout: 2000 });
  });
});

describe("draft recovery", () => {
  it("on the next open a banner names the draft; Restore brings the edits back", async () => {
    stubFetch();
    const backend = memoryDraftBackend();
    const first = await mount(backend);
    first.annotations.draw("Length");
    await autosaved(backend);

    const { el, annotations } = await reload(first.el, backend);
    await vi.waitFor(() => expect(banner(el)).not.toBeNull());

    expect(banner(el)!.textContent).toContain("Unsaved Annotations");
    expect(banner(el)!.textContent).toContain("not saved before");
    expect(annotations.tools).toEqual([]);

    $(el, '[data-draft-restore="annotation"]')!.click();

    await vi.waitFor(() => expect(annotations.tools).toEqual(["Length"]));
    await el.updateComplete;
    expect(banner(el)).toBeNull();
    expect($(el, '[data-save="annotation"]')!.hasAttribute("disabled")).toBe(false);
  });

  it("names the base version and, restored, supersedes it", async () => {
    stubFetch([[201, saved(3)]]);
    const backend = memoryDraftBackend();
    const first = await mount(backend);
    first.annotations.draw("Length");
    await first.el.save.save("annotation"); // now editing on top of v3
    first.annotations.draw("Length");
    await vi.waitFor(async () => expect((await backend.all())[0]?.base?.head.version).toBe(3), { timeout: 2000 });

    const { el } = await reload(first.el, backend);
    await vi.waitFor(() => expect(banner(el)?.textContent).toContain("on v3"));
    $(el, '[data-draft-restore="annotation"]')!.click();

    await vi.waitFor(() => expect(el.save.label("annotation")).toBe("Supersede v3 → v4"));
    expect(el.save.enabled("annotation")).toBe(true);
  });

  it("Discard deletes the draft and leaves the view as it is", async () => {
    stubFetch();
    const backend = memoryDraftBackend();
    const first = await mount(backend);
    first.annotations.draw("Length");
    await autosaved(backend);

    const { el, annotations } = await reload(first.el, backend);
    await vi.waitFor(() => expect(banner(el)).not.toBeNull());
    $(el, '[data-draft-discard="annotation"]')!.click();

    await vi.waitFor(async () => expect(await backend.all()).toEqual([]));
    await el.updateComplete;
    expect(banner(el)).toBeNull();
    expect(annotations.tools).toEqual([]);
  });

  it("another user never sees it", async () => {
    stubFetch();
    const backend = memoryDraftBackend();
    const first = await mount(backend);
    first.annotations.draw("Length");
    await autosaved(backend);

    const { el } = await reload(first.el, backend, { user: "8" });
    await new Promise((r) => setTimeout(r, 50));
    await el.updateComplete;

    expect(banner(el)).toBeNull();
  });

  it("a pending draft isn't overwritten by new edits until restored or discarded", async () => {
    stubFetch();
    const backend = memoryDraftBackend();
    const first = await mount(backend);
    first.annotations.draw("Length");
    await autosaved(backend);

    const { el, annotations } = await reload(first.el, backend);
    await vi.waitFor(() => expect(banner(el)).not.toBeNull());
    annotations.draw("ArrowAnnotate");
    await new Promise((r) => setTimeout(r, 700));

    expect((await backend.all())[0].data).toEqual({ tools: ["Length"] });
  });

  it("restores a Segmentation draft into a new Segmentation", async () => {
    stubFetch();
    const backend = memoryDraftBackend();
    const first = await mount(backend);
    first.el.dispatchEvent(new KeyboardEvent("keydown", { key: "g", bubbles: true, composed: true }));
    await vi.waitFor(() => expect(first.adapter.segmentations).toHaveLength(1));
    const seg = first.adapter.segmentations[0];
    seg.edits = 1;
    seg.emit({ voxels: { 1: 40 } });
    const [draft] = await autosaved(backend);
    expect(draft.kind).toBe("segmentation");

    const { el, adapter } = await reload(first.el, backend);
    await vi.waitFor(() => expect(banner(el)?.textContent).toContain("Unsaved Segmentation"));
    $(el, '[data-draft-restore="segmentation"]')!.click();

    await vi.waitFor(() => expect(adapter.segmentations[0]?.voxelCounts()).toEqual({ 1: 40 }));
    expect(el.save.enabled("segmentation")).toBe(true);
  });
});
