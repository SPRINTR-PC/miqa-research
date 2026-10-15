// #290 Results tree on <mires-viewer>: rows nested under their source series, show/hide (SR and SEG),
// chips, bringing the source series in, History, Retire, Show retired, the Blinded Annotation lock row
// and Blinding Reveal, and the view-only state.
// Seam: the element with the stub adapter, fetch stubbed (WADO /metadata + /frames, the object and blinding API).
import { afterEach, describe, expect, it, vi } from "vitest";

import { StubAdapter } from "./adapter/stub.ts";
import { MiresViewer } from "./mires-viewer.ts";
import { seriesEntries } from "./test-fixtures.ts";

const BASE = "2.25.200";
const OTHER = "2.25.300";
const PET = "2.25.400";

const series = (uid: string, modality: string, description: string) =>
  Array.from({ length: 4 }, (_, i) => ({
    "00080018": { vr: "UI", Value: [`${uid}.${i + 1}`] },
    "00080060": { vr: "CS", Value: [modality] },
    "0008103E": { vr: "LO", Value: [description] },
    "00200013": { vr: "IS", Value: [i + 1] },
    "00200052": { vr: "UI", Value: ["2.25.for"] },
    "00200032": { vr: "DS", Value: [0, 0, i * 2] },
    "00200037": { vr: "DS", Value: [1, 0, 0, 0, 1, 0] },
    "00280030": { vr: "DS", Value: [1, 1] },
    "00280010": { vr: "US", Value: [8] },
    "00280011": { vr: "US", Value: [8] },
  }));

const SR_INSTANCE = { "00080060": { vr: "CS", Value: ["SR"] }, "00080018": { vr: "UI", Value: ["2.25.sr.1"] } };
const SEG_INSTANCE = {
  "00080060": { vr: "CS", Value: ["SEG"] },
  "00080018": { vr: "UI", Value: ["2.25.seg.1"] },
  "00280008": { vr: "IS", Value: [2] },
};

interface Chain {
  id: string;
  chain_id: string;
  kind: string;
  source: string;
  version: number;
  series_instance_uid: string;
  series_description: string | null;
  modality: string;
  author: string | null;
  created_at: string;
  retired: boolean;
  source_series_uids: string[];
  base_series_uid: string;
  can_change: boolean;
  history: Omit<Chain, "history" | "can_change">[];
}

function chain(id: string, extra: Partial<Chain> = {}): Chain {
  const kind = extra.kind ?? "annotation";
  const version = extra.version ?? 1;
  const head = {
    id: `${id}-v${version}`,
    chain_id: id,
    kind,
    source: "viewer",
    version,
    series_instance_uid: `2.25.${kind === "annotation" ? "sr" : "seg"}.${id}`,
    series_description: kind === "annotation" ? "Annotations" : "Segmentation",
    modality: kind === "annotation" ? "SR" : "SEG",
    author: "anna",
    created_at: "2026-10-08T11:30:00Z",
    retired: false,
    source_series_uids: [BASE],
    base_series_uid: BASE,
    ...extra,
  };
  const history = Array.from({ length: version }, (_, i) => ({
    ...head,
    id: `${id}-v${i + 1}`,
    version: i + 1,
    author: i + 1 === version ? head.author : "bertil",
    created_at: `2026-10-0${i + 1}T09:00:00Z`,
  }));
  return { can_change: true, history, ...head };
}

interface Server {
  chains: Chain[];
  retired: Chain[];
  blinding: { blinded: boolean; revealed: boolean; can_reveal: boolean; hidden: number };
  /** Chains that appear once the Blinding Reveal is made. */
  hiddenChains: Chain[];
  calls: { url: string; method: string; viewerSession: string | null }[];
}

function stubServer(initial: Partial<Server> = {}): Server {
  const server: Server = {
    chains: [],
    retired: [],
    blinding: { blinded: false, revealed: false, can_reveal: false, hidden: 0 },
    hiddenChains: [],
    calls: [],
    ...initial,
  };
  const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      server.calls.push({ url, method, viewerSession: new Headers(init?.headers).get("X-Mires-Viewer-Session") });
      const retire = url.match(/\/objects\/([^/]+)\/retire$/);
      if (retire && method === "POST") {
        const found = server.chains.find((c) => c.id === retire[1])!;
        server.chains = server.chains.filter((c) => c !== found);
        server.retired.push({ ...found, retired: true });
        return json({ ...found, retired: true });
      }
      if (url.includes("/blinding-reveal") && method === "POST") {
        server.blinding = { ...server.blinding, revealed: true, hidden: 0 };
        server.chains.push(...server.hiddenChains);
        return json(server.blinding);
      }
      if (url.includes("/blinding")) return json(server.blinding);
      if (url.includes("/objects?")) {
        return json(url.includes("include_retired=true") ? [...server.chains, ...server.retired] : server.chains);
      }
      if (url.includes("/frames/")) {
        const boundary = "b0";
        const body = `--${boundary}\r\nContent-Type: application/octet-stream\r\n\r\n\x01\x02\r\n--${boundary}\r\nContent-Type: application/octet-stream\r\n\r\n\x03\x04\r\n--${boundary}--\r\n`;
        return new Response(body, { headers: { "Content-Type": `multipart/related; type="application/octet-stream"; boundary=${boundary}` } });
      }
      if (url.includes("/series/2.25.sr.")) return json([SR_INSTANCE]);
      if (url.includes("/series/2.25.seg.")) return json([SEG_INSTANCE]);
      if (url.includes(`/series/${OTHER}/`)) return json(series(OTHER, "CT", "Other CT"));
      if (url.includes(`/series/${PET}/`)) return json(series(PET, "PT", "PET"));
      return json(series(BASE, "CT", "Chest CT"));
    }),
  );
  return server;
}

async function mount({ canAnnotate = true, related = [OTHER, PET], ...initial }: Partial<Server> & { canAnnotate?: boolean; related?: string[] } = {}) {
  const server = stubServer(initial);
  const adapter = new StubAdapter();
  const el = document.createElement("mires-viewer") as MiresViewer;
  el.adapterFactory = async () => adapter;
  el.entries = seriesEntries([BASE], related, "2.25.100", { [BASE]: { modality: "CT" }, [PET]: { modality: "PT" } });
  el.setAttribute("participant", "p1");
  el.canAnnotate = canAnnotate;
  document.body.append(el);
  await vi.waitFor(() => expect(el.getAttribute("state")).toBe("ready"));
  await vi.waitFor(() => expect(el.shadowRoot!.querySelectorAll(".ser")).toHaveLength(1 + related.length));
  await vi.waitFor(() => expect(el.results.loaded).toBe(true));
  await el.updateComplete;
  return { el, adapter, server };
}

const $ = (el: MiresViewer, selector: string) => el.shadowRoot!.querySelector<HTMLElement>(selector);
const $$ = (el: MiresViewer, selector: string) => [...el.shadowRoot!.querySelectorAll<HTMLElement>(selector)];
const row = (el: MiresViewer, chainId: string) => $(el, `.result[data-chain="${chainId}"]`);

async function click(el: MiresViewer, selector: string) {
  const target = $(el, selector);
  if (!target) throw new Error(`nothing matches ${selector}`);
  target.click();
  await el.updateComplete;
}

async function settle(el: MiresViewer) {
  await vi.waitFor(() => expect(el.results.busy).toBeUndefined());
  await el.updateComplete;
}

afterEach(() => {
  document.body.innerHTML = "";
  vi.unstubAllGlobals();
});

describe("the results tree", () => {
  it("nests each object's head under its source series, a Fusion's under the base with a ⊕ badge", async () => {
    const { el } = await mount({
      chains: [
        chain("a1", { version: 2 }),
        chain("s1", { kind: "segmentation", source_series_uids: [BASE, PET].sort(), base_series_uid: BASE }),
        chain("o1", { source_series_uids: [OTHER], base_series_uid: OTHER }),
      ],
    });

    const under = (uid: string) => $$(el, `.ser-group[data-series-uid="${uid}"] .result`).map((r) => r.dataset.chain);
    expect(under(BASE)).toEqual(["a1", "s1"]);
    expect(under(OTHER)).toEqual(["o1"]);
    expect(row(el, "a1")!.textContent).toContain("Annotations");
    expect(row(el, "a1")!.textContent).toContain("v2");
    expect(row(el, "a1")!.textContent).toContain("anna");
    expect(row(el, "s1")!.querySelector(".fusion")!.textContent).toBe("⊕ PT");
    expect(row(el, "a1")!.querySelector(".fusion")).toBeNull();
  });
});

describe("showing and hiding", () => {
  it("click shows an SR head on the base series with a chip; the chip's ✕ hides it", async () => {
    const { el, adapter, server } = await mount({ chains: [chain("a1", { version: 2 })] });
    const annotations = adapter.annotations!;

    await click(el, '.result[data-chain="a1"] .show');
    await settle(el);

    expect(server.calls.some((c) => c.url.endsWith("/series/2.25.sr.a1/metadata"))).toBe(true);
    expect(annotations.imported).toHaveLength(1);
    expect(annotations.imported[0].instance).toEqual(SR_INSTANCE);
    expect(annotations.imported[0].series.ref.seriesUid).toBe(BASE);
    expect(row(el, "a1")!.classList).toContain("shown");
    expect($(el, '.chip[data-chain="a1"]')!.textContent).toContain("Annotations v2 · anna");
    // Save now supersedes the head shown.
    expect($(el, '[data-save="annotation"]')!.textContent).toContain("Supersede v2 → v3");

    await click(el, '.chip[data-chain="a1"] button');

    expect(annotations.removed).toEqual(["sr-1"]);
    expect(annotations.count()).toBe(0);
    expect($(el, ".chip")).toBeNull();
    expect(row(el, "a1")!.classList).not.toContain("shown");
    expect($(el, '[data-save="annotation"]')!.textContent).toContain("Save as new (v1)");
  });

  it("click again on the row hides it", async () => {
    const { el, adapter } = await mount({ chains: [chain("a1")] });
    await click(el, '.result[data-chain="a1"] .show');
    await settle(el);

    await click(el, '.result[data-chain="a1"] .show');

    expect(adapter.annotations!.count()).toBe(0);
    expect($(el, ".chip")).toBeNull();
  });

  it("shows a SEG head from its /metadata and /frames as the Segmentation, and hides it", async () => {
    const { el, adapter, server } = await mount({ chains: [chain("s1", { kind: "segmentation" })] });

    await click(el, '.result[data-chain="s1"] .show');
    await settle(el);

    const frames = server.calls.find((c) => c.url.includes("/frames/"))!;
    expect(frames.url).toContain("/series/2.25.seg.s1/instances/2.25.seg.1/frames/1,2");
    const [seg] = adapter.segmentations;
    expect(seg.saved!.instance).toEqual(SEG_INSTANCE);
    expect(seg.saved!.frames.map((f) => [...f])).toEqual([[1, 2], [3, 4]]);
    expect(seg.shownIn).toContain(adapter.views[0]);
    expect($(el, '.chip[data-chain="s1"]')!.textContent).toContain("Segmentation v1");
    expect($(el, '[data-save="segmentation"]')!.textContent).toContain("Supersede v1 → v2");
    expect($(el, '[data-save="segmentation"]')!.hasAttribute("disabled")).toBe(true); // nothing edited yet

    await click(el, '.chip[data-chain="s1"] button');

    expect(seg.closed).toBe(true);
    expect(el.segmentationState).toBeUndefined();
  });

  it("showing another SEG replaces the shown one: one Segmentation at a time", async () => {
    const { el, adapter } = await mount({ chains: [chain("s1", { kind: "segmentation" }), chain("s2", { kind: "segmentation" })] });
    await click(el, '.result[data-chain="s1"] .show');
    await settle(el);

    await click(el, '.result[data-chain="s2"] .show');
    await settle(el);

    expect(adapter.segmentations[0].closed).toBe(true);
    expect($$(el, ".chip").map((c) => c.dataset.chain)).toEqual(["s2"]);
  });

  it("brings a source series that isn't in view in (replace), then shows the head on it", async () => {
    const { el, adapter } = await mount({ chains: [chain("o1", { source_series_uids: [OTHER], base_series_uid: OTHER })] });

    await click(el, '.result[data-chain="o1"] .show');
    await settle(el);

    expect(adapter.opened.at(-1)!.series.ref.seriesUid).toBe(OTHER);
    expect($$(el, ".ser.shown").map((r) => r.dataset.seriesUid)).toEqual([OTHER]);
    expect(adapter.annotations!.imported[0].series.ref.seriesUid).toBe(OTHER);
    expect(row(el, "o1")!.classList).toContain("shown");
  });

  it("hides the heads of a series that another series replaced", async () => {
    const { el, adapter } = await mount({
      chains: [chain("a1"), chain("o1", { source_series_uids: [OTHER], base_series_uid: OTHER })],
    });
    await click(el, '.result[data-chain="a1"] .show');
    await settle(el);

    await click(el, '.result[data-chain="o1"] .show');
    await settle(el);

    expect(adapter.annotations!.removed).toEqual(["sr-1"]);
    expect($$(el, ".chip").map((c) => c.dataset.chain)).toEqual(["o1"]);
  });

  it("won't drop unsaved Segmentation edits to show a saved SEG", async () => {
    const { el, adapter } = await mount({ chains: [chain("s1", { kind: "segmentation" })] });
    el.dispatchEvent(new KeyboardEvent("keydown", { key: "g", bubbles: true, composed: true }));
    await vi.waitFor(() => expect(adapter.segmentations).toHaveLength(1));
    adapter.segmentations[0].edits = 1;
    adapter.segmentations[0].emit({ voxels: { 1: 10 } });

    await click(el, '.result[data-chain="s1"] .show');
    await settle(el);

    expect(adapter.segmentations).toHaveLength(1);
    expect(adapter.segmentations[0].closed).toBe(false);
    expect($(el, ".chip")).toBeNull();
    expect(el.shadowRoot!.textContent).toContain("Save your Segmentation edits first");
  });
});

describe("row menu", () => {
  it("History lists the version trail, newest first, with author and date, the head marked", async () => {
    const { el } = await mount({ chains: [chain("a1", { version: 2 })] });

    await click(el, '.result[data-chain="a1"] .more');
    await click(el, '.result-menu [data-action="history"]');

    const items = $$(el, ".result-history li");
    expect(items.map((li) => li.dataset.version)).toEqual(["2", "1"]);
    expect(items[0].classList).toContain("head");
    expect(items[0].textContent).toContain("anna");
    expect(items[1].textContent).toContain("bertil");
    expect(items[1].textContent).toContain(new Date("2026-10-01T09:00:00Z").toLocaleString());
  });

  it("Retire asks first, then retires the head: the row and its chip go, a toast confirms", async () => {
    const { el, server } = await mount({ chains: [chain("a1", { version: 2 }), chain("a2")] });
    await click(el, '.result[data-chain="a1"] .show');
    await settle(el);

    await click(el, '.result[data-chain="a1"] .more');
    await click(el, '.result-menu [data-action="retire"]');
    expect($(el, ".results-confirm")!.textContent).toContain("disappears from lists and counts");
    expect(server.calls.some((c) => c.url.endsWith("/retire"))).toBe(false);

    await click(el, '[data-confirm="ok"]');
    await vi.waitFor(() => expect(row(el, "a1")).toBeNull());

    expect(server.calls.filter((c) => c.method === "POST").map((c) => c.url)).toEqual(["/api/v1/viewer/objects/a1-v2/retire"]);
    expect($(el, ".chip")).toBeNull();
    expect($(el, ".results-confirm")).toBeNull();
    expect($(el, ".toast")!.textContent).toContain("retired");
    expect(row(el, "a2")).not.toBeNull();
  });

  it("Cancel keeps the object", async () => {
    const { el, server } = await mount({ chains: [chain("a1")] });
    await click(el, '.result[data-chain="a1"] .more');
    await click(el, '.result-menu [data-action="retire"]');

    await click(el, '[data-confirm="cancel"]');

    expect($(el, ".results-confirm")).toBeNull();
    expect(server.calls.some((c) => c.method === "POST")).toBe(false);
    expect(row(el, "a1")).not.toBeNull();
  });

  it("offers Retire only on objects the user may change", async () => {
    const { el } = await mount({ chains: [chain("a1", { can_change: false })] });
    await click(el, '.result[data-chain="a1"] .more');

    expect($(el, '.result-menu [data-action="history"]')).not.toBeNull();
    expect($(el, '.result-menu [data-action="retire"]')).toBeNull();
  });

  it("Show retired lists retired objects read-only", async () => {
    const { el, server } = await mount({ retired: [chain("r1", { retired: true })] });
    expect(row(el, "r1")).toBeNull();

    const toggle = $(el, ".show-retired") as HTMLInputElement;
    toggle.checked = true;
    toggle.dispatchEvent(new Event("change"));
    await vi.waitFor(() => expect(row(el, "r1")).not.toBeNull());
    await el.updateComplete;

    expect(server.calls.some((c) => c.url.includes("include_retired=true"))).toBe(true);
    expect(row(el, "r1")!.classList).toContain("retired");
    expect((row(el, "r1")!.querySelector(".show") as HTMLButtonElement).disabled).toBe(true);
    await click(el, '.result[data-chain="r1"] .more');
    expect($(el, '.result-menu [data-action="retire"]')).toBeNull();
  });
});

describe("Blinded Annotation", () => {
  const blinded = { blinded: true, revealed: false, can_reveal: true, hidden: 2 };

  it("a lock row says only your own work is shown and how much is hidden", async () => {
    const { el } = await mount({ blinding: { ...blinded, can_reveal: false } });

    expect($(el, ".lock-row")!.textContent).toContain("showing only your own work");
    expect($(el, ".lock-row .hidden-count")!.textContent).toBe("2");
    expect($(el, '[data-action="reveal"]')).toBeNull(); // annotators get no button
  });

  it("PI, Site PI and Admin reveal for this participant after an audit-logged confirm", async () => {
    const { el, server } = await mount({ blinding: blinded, hiddenChains: [chain("h1", { author: "cecilia" })] });
    expect(row(el, "h1")).toBeNull();

    await click(el, '[data-action="reveal"]');
    const confirm = $(el, ".results-confirm")!;
    expect(confirm.textContent).toContain("this viewer session");
    expect(confirm.textContent).toContain("audit-logged");

    await click(el, '[data-confirm="ok"]');
    await vi.waitFor(() => expect(row(el, "h1")).not.toBeNull());
    await el.updateComplete;

    expect(server.calls.filter((c) => c.method === "POST").map((c) => c.url)).toEqual(["/api/v1/viewer/participants/p1/blinding-reveal"]);
    expect($(el, ".lock-row")!.textContent).toContain("Blinding Reveal active");
    expect($(el, '[data-action="reveal"]')).toBeNull();
  });

  it("every request of this viewer open carries one Viewer Session id: the reveal lasts for this open only", async () => {
    const hidden = [chain("h1", { kind: "segmentation", author: "cecilia" }), chain("h2", { author: "cecilia" })];
    const { el, server } = await mount({ blinding: blinded, hiddenChains: hidden });
    await click(el, '[data-action="reveal"]');
    await click(el, '[data-confirm="ok"]');
    await vi.waitFor(() => expect(row(el, "h1")).not.toBeNull());
    await el.updateComplete;
    await click(el, '.result[data-chain="h1"] .show');
    await settle(el);
    await click(el, '.result[data-chain="h2"] .show');
    await settle(el);

    const urls = server.calls.map((c) => c.url);
    expect(urls.some((u) => u.includes("/series/2.25.seg.h1/instances/") && u.includes("/frames/"))).toBe(true);
    expect(urls.some((u) => u.endsWith("/series/2.25.sr.h2/metadata"))).toBe(true);
    const ids = new Set(server.calls.map((c) => c.viewerSession));
    expect(ids.size).toBe(1);
    expect([...ids][0]).toMatch(/^[0-9a-f-]{36}$/);
  });

  it("no lock row on a project without Blinded Annotation", async () => {
    const { el } = await mount();
    expect($(el, ".lock-row")).toBeNull();
  });
});

describe("view-only roles", () => {
  it("see the same tree and can show heads, with no save, retire, show retired or reveal", async () => {
    const { el, adapter } = await mount({
      canAnnotate: false,
      chains: [chain("a1", { can_change: false })],
      blinding: { blinded: true, revealed: false, can_reveal: false, hidden: 1 },
    });

    await click(el, '.result[data-chain="a1"] .show');
    await settle(el);
    expect(adapter.annotations!.imported).toHaveLength(1);
    expect($(el, '.chip[data-chain="a1"]')).not.toBeNull();

    await click(el, '.result[data-chain="a1"] .more');
    expect($(el, '.result-menu [data-action="retire"]')).toBeNull();
    expect($(el, ".show-retired")).toBeNull();
    expect($(el, '[data-action="reveal"]')).toBeNull();
    expect($(el, "[data-save]")).toBeNull();
  });
});

describe("without a participant", () => {
  it("lists nothing and asks the object API nothing", async () => {
    const server = stubServer({ chains: [chain("a1")] });
    const el = document.createElement("mires-viewer") as MiresViewer;
    el.adapterFactory = async () => new StubAdapter();
    el.entries = seriesEntries([BASE], [], "2.25.100");
    document.body.append(el);
    await vi.waitFor(() => expect(el.getAttribute("state")).toBe("ready"));
    await el.updateComplete;

    expect(server.calls.some((c) => c.url.includes("/viewer/"))).toBe(false);
    expect($(el, ".result")).toBeNull();
  });
});
