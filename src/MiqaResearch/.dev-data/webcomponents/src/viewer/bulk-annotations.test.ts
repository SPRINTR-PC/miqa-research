// Bulk ANN read-only layer on WSI (#292): <mires-viewer> against the stub adapter.
import { afterEach, describe, expect, it, vi } from "vitest";

import { StubAdapter } from "./adapter/stub.ts";
import { MiresViewer } from "./mires-viewer.ts";
import { seriesEntries } from "./test-fixtures.ts";

const WSI_SOP_CLASS = "1.2.840.10008.5.1.4.1.1.77.1.6";
const ANN_SOP_CLASS = "1.2.840.10008.5.1.4.1.1.91.1";
const PARTICIPANT = "01a11941-fadb-74d8-91be-a106fa9c8001";

const SLIDE = [{ "00080016": { vr: "UI", Value: [WSI_SOP_CLASS] }, "00080018": { vr: "UI", Value: ["2.25.1"] } }];

const code = (meaning: string) => ({ vr: "SQ", Value: [{ "00080104": { vr: "LO", Value: [meaning] } }] });
const group = (uid: string, number: number, type: string, count: number) => ({
  "006A0003": { vr: "UI", Value: [uid] },
  "0040A180": { vr: "US", Value: [number] },
  "006A0005": { vr: "LO", Value: ["ANONYMIZED"] },
  "006A000A": code(type),
  "006A000C": { vr: "UL", Value: [count] },
  "00700023": { vr: "CS", Value: ["POLYGON"] },
  "00660016": { vr: "OF", InlineBinary: "AAAA" },
});
const ANN = [
  {
    "00080016": { vr: "UI", Value: [ANN_SOP_CLASS] },
    "00080018": { vr: "UI", Value: ["2.25.9"] },
    "006A0002": { vr: "SQ", Value: [group("2.25.71", 1, "Neoplasm", 2), group("2.25.72", 2, "Connective tissue", 1)] },
  },
];

const chain = (modality: string, series: string) => ({ kind: "annotation", modality, series_instance_uid: series });

function stubServer(objects: unknown[] = [chain("ANN", "2.25.500"), chain("SR", "2.25.600")]) {
  const fetch = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.startsWith("/api/v1/viewer/objects?")) return new Response(JSON.stringify(objects));
    if (url.endsWith("/series/2.25.200/metadata")) return new Response(JSON.stringify(SLIDE));
    if (url.endsWith("/series/2.25.500/metadata")) return new Response(JSON.stringify(ANN));
    return new Response("", { status: 404 });
  });
  vi.stubGlobal("fetch", fetch);
  return fetch;
}

async function mount(adapter: StubAdapter, participant = PARTICIPANT): Promise<MiresViewer> {
  const el = document.createElement("mires-viewer") as MiresViewer;
  el.adapterFactory = async () => adapter;
  el.entries = seriesEntries(["2.25.200"], [], "2.25.100");
  if (participant) el.setAttribute("participant", participant);
  document.body.append(el);
  await vi.waitFor(() => expect(el.getAttribute("state")).toMatch(/ready|error/));
  await el.updateComplete;
  return el;
}

const toggles = (el: MiresViewer) => [...el.shadowRoot!.querySelectorAll<HTMLInputElement>("[data-ann-group]")];

afterEach(() => {
  document.body.innerHTML = "";
  vi.unstubAllGlobals();
});

describe("bulk annotations (ANN) on a slide", () => {
  it("loads the slide's ANN through the object list and lists its groups, all shown", async () => {
    const fetch = stubServer();
    const adapter = new StubAdapter();

    const el = await mount(adapter);
    await vi.waitFor(() => expect(toggles(el)).toHaveLength(2));

    expect(fetch).toHaveBeenCalledWith(`/api/v1/viewer/objects?participant=${PARTICIPANT}&series=2.25.200`, expect.anything());
    expect(adapter.wsiViews[0].bulkInstances).toEqual(ANN); // only the ANN series, not the SR
    const panel = el.shadowRoot!.querySelector(".inspector")!.textContent!;
    expect(panel).toContain("Neoplasm");
    expect(panel).toContain("Connective tissue");
    expect(toggles(el).map((t) => [t.dataset.annGroup, t.checked])).toEqual([
      ["2.25.71", true],
      ["2.25.72", true],
    ]);
  });

  it("toggling a group hides and shows it", async () => {
    stubServer();
    const adapter = new StubAdapter();
    const el = await mount(adapter);
    await vi.waitFor(() => expect(toggles(el)).toHaveLength(2));

    toggles(el)[0].click();
    await el.updateComplete;

    expect(adapter.wsiViews[0].bulkAnnotationGroups().map((g) => g.visible)).toEqual([false, true]);
    expect(toggles(el)[0].checked).toBe(false);

    toggles(el)[0].click();
    await el.updateComplete;
    expect(adapter.wsiViews[0].bulkAnnotationGroups().map((g) => g.visible)).toEqual([true, true]);
  });

  it("offers no editing: the panel has only show/hide toggles", async () => {
    stubServer();
    const el = await mount(new StubAdapter());
    await vi.waitFor(() => expect(toggles(el)).toHaveLength(2));

    const section = el.shadowRoot!.querySelector("[data-panel=bulk-annotations]")!;
    expect(section.querySelectorAll("button, [contenteditable], input:not([type=checkbox])")).toHaveLength(0);
    expect(section.textContent).toMatch(/read-only/i);
  });

  it("shows no panel when the slide has no ANN, or without a participant", async () => {
    stubServer([chain("SR", "2.25.600")]);
    const withoutAnn = await mount(new StubAdapter());
    const fetch = stubServer();
    const withoutParticipant = await mount(new StubAdapter(), "");

    await new Promise((r) => setTimeout(r, 10));
    expect(withoutAnn.shadowRoot!.querySelector("[data-panel=bulk-annotations]")).toBeNull();
    expect(withoutParticipant.shadowRoot!.querySelector("[data-panel=bulk-annotations]")).toBeNull();
    expect(fetch.mock.calls.some(([url]) => String(url).includes("/viewer/objects"))).toBe(false);
  });
});
