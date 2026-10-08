// #289 Save on <mires-viewer>: the inspector's save buttons, Ctrl/⌘+S, the toast and the 409 dialog.
// Seam: the element with the stub adapter, fetch stubbed (WADO /metadata and the object API).
import { afterEach, describe, expect, it, vi } from "vitest";

import { StubAdapter } from "./adapter/stub.ts";
import { MiresViewer } from "./mires-viewer.ts";

const ct = (n: number) =>
  Array.from({ length: n }, (_, i) => ({
    "00080018": { vr: "UI", Value: [`2.25.${i + 1}`] },
    "00080060": { vr: "CS", Value: ["CT"] },
    "00200013": { vr: "IS", Value: [i + 1] },
    "00280010": { vr: "US", Value: [64] },
    "00280011": { vr: "US", Value: [64] },
  }));

const version = (v: number, extra: Record<string, unknown> = {}) => ({
  id: `id-${v}`,
  chain_id: "c1",
  kind: "annotation",
  version: v,
  author: "bertil",
  created_at: "2026-10-08T11:30:00Z",
  series_instance_uid: `2.25.sr${v}`,
  ...extra,
});

type Reply = [number, unknown];

/** fetch: series /metadata for GETs; queued replies for POST /objects (and SR /metadata GETs after the first). */
function stubFetch(posts: Reply[], srMetadata: unknown[] = []) {
  const calls: { url: string; init?: RequestInit }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      calls.push({ url, init });
      if (init?.method === "POST") {
        const [status, body] = posts.shift()!;
        return new Response(JSON.stringify(body), { status });
      }
      if (url.includes("/frames/")) {
        const body = "--b\r\nContent-Type: application/octet-stream\r\n\r\n\x07\r\n--b--\r\n";
        return new Response(body, { headers: { "Content-Type": 'multipart/related; type="application/octet-stream"; boundary=b' } });
      }
      if (url.includes("/series/2.25.sr")) return new Response(JSON.stringify(srMetadata));
      return new Response(JSON.stringify(ct(4)));
    }),
  );
  return calls;
}

async function mount({ canAnnotate = true, posts = [] as Reply[], srMetadata = [] as unknown[] } = {}) {
  const calls = stubFetch(posts, srMetadata);
  const adapter = new StubAdapter();
  const el = document.createElement("mires-viewer") as MiresViewer;
  el.adapterFactory = async () => adapter;
  el.setAttribute("study-uid", "2.25.100");
  el.setAttribute("series-uid", "2.25.200");
  el.canAnnotate = canAnnotate;
  document.body.append(el);
  await vi.waitFor(() => expect(el.getAttribute("state")).toBe("ready"));
  await el.updateComplete;
  return { el, adapter, annotations: adapter.annotations!, calls };
}

const $ = (el: MiresViewer, selector: string) => el.shadowRoot!.querySelector<HTMLButtonElement>(selector);
const posted = (calls: { init?: RequestInit }[]) => calls.filter((c) => c.init?.method === "POST").map((c) => c.init!.body as FormData);

async function settle(el: MiresViewer) {
  await vi.waitFor(() => expect(el.save.saving).toBeUndefined());
  await el.updateComplete;
}

afterEach(() => {
  document.body.innerHTML = "";
  vi.unstubAllGlobals();
});

describe("save buttons", () => {
  it("sit at the top of the inspector, one per kind, enabled when there are edits", async () => {
    const { el, annotations } = await mount();
    expect(el.shadowRoot!.querySelector(".inspector section.panel")!.classList).toContain("save");
    expect($(el, '[data-save="annotation"]')!.disabled).toBe(true);
    expect($(el, '[data-save="segmentation"]')!.disabled).toBe(true);
    expect($(el, '[data-save="annotation"]')!.textContent).toContain("Save as new (v1)");

    annotations.draw("Length");
    await el.updateComplete;

    expect($(el, '[data-save="annotation"]')!.disabled).toBe(false);
    expect($(el, '[data-save="segmentation"]')!.disabled).toBe(true);
  });

  it("save the SR of the base series, toast, then offer to supersede what was saved", async () => {
    const { el, annotations, calls } = await mount({ posts: [[201, version(1, { author: "me" })]] });
    annotations.draw("Length");
    await el.updateComplete;

    $(el, '[data-save="annotation"]')!.click();
    await settle(el);

    const [form] = posted(calls);
    expect(form.getAll("source_series")).toEqual(["2.25.200"]);
    expect(annotations.exported.map((s) => s.ref.seriesUid)).toEqual(["2.25.200"]);
    expect($(el, ".toast")!.textContent).toBe("Annotations saved (v1)");
    expect($(el, '[data-save="annotation"]')!.disabled).toBe(true);
    expect($(el, '[data-save="annotation"]')!.textContent).toContain("Supersede v1 → v2");
  });

  it("save the painted Segmentation as SEG", async () => {
    const { el, adapter, calls } = await mount({ posts: [[201, version(1, { kind: "segmentation" })]] });
    el.dispatchEvent(new KeyboardEvent("keydown", { key: "g", bubbles: true, composed: true }));
    await vi.waitFor(() => expect(adapter.segmentations).toHaveLength(1));
    const seg = adapter.segmentations[0];
    seg.edits = 1;
    seg.emit({ voxels: { 1: 20 } });
    await el.updateComplete;

    $(el, '[data-save="segmentation"]')!.click();
    await settle(el);

    expect(posted(calls)).toHaveLength(1);
    expect($(el, ".toast")!.textContent).toBe("Segmentation saved (v1)");
  });

  it("warn when annotations of tools the SR can't hold would be dropped", async () => {
    const { el, annotations } = await mount();
    annotations.draw("Length", "LivewireContour");
    await el.updateComplete;

    expect($(el, ".save-dropped")!.textContent).toContain("LivewireContour");
  });

  it("Ctrl/⌘+S saves every kind with edits", async () => {
    const { el, annotations, calls } = await mount({ posts: [[201, version(1)]] });
    annotations.draw("Length");
    await el.updateComplete;

    el.dispatchEvent(new KeyboardEvent("keydown", { key: "s", metaKey: true, bubbles: true, composed: true }));
    await settle(el);

    expect(posted(calls)).toHaveLength(1);
  });

  it("are not shown to view-only roles, and Ctrl/⌘+S does nothing", async () => {
    const { el, annotations, calls } = await mount({ canAnnotate: false });
    annotations.draw("Length");
    await el.updateComplete;

    expect($(el, "[data-save]")).toBeNull();
    el.dispatchEvent(new KeyboardEvent("keydown", { key: "s", ctrlKey: true, bubbles: true, composed: true }));
    await el.updateComplete;
    expect(posted(calls)).toHaveLength(0);
  });
});

describe("the 409 dialog", () => {
  const stale = (canChange: boolean): Reply => [409, { detail: "a newer version was saved first", head: version(2), can_change: canChange }];

  async function conflicted(canChange: boolean, then: Reply[] = [], srMetadata: unknown[] = []) {
    const mounted = await mount({ posts: [[201, version(1, { author: "me" })], stale(canChange), ...then], srMetadata });
    const { el, annotations } = mounted;
    annotations.draw("Length");
    await el.updateComplete;
    $(el, '[data-save="annotation"]')!.click();
    await settle(el);
    annotations.draw("Angle");
    await el.updateComplete;
    $(el, '[data-save="annotation"]')!.click();
    await settle(el);
    return mounted;
  }

  it("names who saved which version and offers the three outcomes", async () => {
    const { el } = await conflicted(true);
    const dialog = $(el, '[role="dialog"]')!;
    expect(dialog.textContent).toContain("bertil saved v2");
    const choices = [...dialog.querySelectorAll<HTMLElement>("[data-choice]")].map((b) => b.dataset.choice);
    expect(choices).toEqual(["load-theirs", "separate", "on-top", "cancel"]);
  });

  it("offers Save mine on top only if allowed", async () => {
    const { el } = await conflicted(false);
    expect($(el, '[data-choice="on-top"]')).toBeNull();
  });

  it("Discard mine, load theirs: clears the annotations and shows the head's SR", async () => {
    const sr = { "00080060": { vr: "CS", Value: ["SR"] } };
    const { el, annotations } = await conflicted(false, [], [sr]);

    $(el, '[data-choice="load-theirs"]')!.click();
    await vi.waitFor(() => expect(annotations.imported).toHaveLength(1));
    await el.updateComplete;

    expect(annotations.cleared).toBe(1);
    expect(annotations.imported[0].instance).toEqual(sr);
    expect($(el, '[role="dialog"]')).toBeNull();
    expect($(el, '[data-save="annotation"]')!.disabled).toBe(true);
    expect($(el, '[data-save="annotation"]')!.textContent).toContain("Save as new (v1)");
  });

  it("Discard mine, load theirs on a SEG: drops the local labelmap and shows their SEG (#290)", async () => {
    const seg = { "00080060": { vr: "CS", Value: ["SEG"] }, "00080018": { vr: "UI", Value: ["2.25.seg"] } };
    const { el, adapter } = await mount({
      posts: [[409, { detail: "stale", head: version(2, { kind: "segmentation" }), can_change: false }]],
      srMetadata: [seg],
    });
    el.dispatchEvent(new KeyboardEvent("keydown", { key: "g", bubbles: true, composed: true }));
    await vi.waitFor(() => expect(adapter.segmentations).toHaveLength(1));
    adapter.segmentations[0].edits = 1;
    adapter.segmentations[0].emit({ voxels: { 1: 20 } });
    await el.updateComplete;
    $(el, '[data-save="segmentation"]')!.click();
    await settle(el);

    $(el, '[data-choice="load-theirs"]')!.click();
    await vi.waitFor(() => expect(adapter.segmentations).toHaveLength(2));
    await el.updateComplete;

    expect(adapter.segmentations[0].closed).toBe(true);
    expect(adapter.segmentations[1].saved!.instance).toEqual(seg);
    expect(adapter.segmentations[1].saved!.frames.map((f) => [...f])).toEqual([[7]]);
    expect($(el, '[data-save="segmentation"]')!.disabled).toBe(true);
  });

  it("Save mine as a separate object, or on top", async () => {
    const separate = await conflicted(true, [[201, version(1, { chain_id: "c2" })]]);
    $(separate.el, '[data-choice="separate"]')!.click();
    await settle(separate.el);
    expect(posted(separate.calls)[2].get("supersedes")).toBeNull();
    expect($(separate.el, '[role="dialog"]')).toBeNull();

    document.body.innerHTML = "";
    const onTop = await conflicted(true, [[201, version(3)]]);
    $(onTop.el, '[data-choice="on-top"]')!.click();
    await settle(onTop.el);
    expect(posted(onTop.calls)[2].get("supersedes")).toBe("id-2");
    expect($(onTop.el, '[data-save="annotation"]')!.textContent).toContain("Supersede v3 → v4");
  });
});
