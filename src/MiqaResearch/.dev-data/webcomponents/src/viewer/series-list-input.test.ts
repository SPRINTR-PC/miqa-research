// #279 entry contract (#184) on <mires-viewer>: the page hands one JSON series list (the opened series,
// first = base, the rest fused onto it, then the Related Series, possibly of other studies) and the page's
// Viewer Session id. Seam: the element with the stub adapter; /metadata served by a stubbed fetch.
import { afterEach, describe, expect, it, vi } from "vitest";

import { StubAdapter } from "./adapter/stub.ts";
import { MiresViewer } from "./mires-viewer.ts";
import type { DicomJsonInstance } from "./series.ts";
import type { SeriesEntry } from "./chrome/series-list.ts";
import { petInstance, volumeInstances } from "./test-fixtures.ts";
import { VIEWER_SESSION_HEADER } from "./viewer-session.ts";

const METADATA: Record<string, DicomJsonInstance[]> = {
  ct: volumeInstances(8, { description: "Chest CT" }),
  pet: volumeInstances(8, { modality: "PT", description: "PET AC", extra: petInstance() }),
  mr: volumeInstances(8, { modality: "MR", description: "Brain MR", frameOfReference: "2.25.99" }),
};

const entry = (series: string, study: string, open: boolean, modality = "CT", description = series): SeriesEntry => ({
  study, series, modality, description, instances: 8, frame_of_reference: "2.25.7", open,
});

const ENTRIES = [
  entry("ct", "study-1", true, "CT", "Chest CT"),
  entry("pet", "study-1", true, "PT", "PET AC"),
  entry("mr", "study-2", false, "MR", "Brain MR (2025)"),
];

let fetched: { url: string; headers: Record<string, string> }[] = [];

function stubFetch() {
  fetched = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      fetched.push({ url, headers: (init?.headers ?? {}) as Record<string, string> });
      const match = /series\/([^/]+)\/metadata/.exec(url);
      return new Response(JSON.stringify(match ? METADATA[match[1]] : []));
    }),
  );
}

async function mount(configure: (el: MiresViewer) => void) {
  stubFetch();
  const adapter = new StubAdapter();
  adapter.gpu = { max3dTextureSize: 2048, maxTextureSize: 16384 };
  const el = document.createElement("mires-viewer") as MiresViewer;
  el.adapterFactory = async () => adapter;
  configure(el);
  document.body.append(el);
  await vi.waitFor(() => expect(el.getAttribute("state")).toBe("ready"));
  await vi.waitFor(() => expect(el.fusionBusy).toBe(false));
  await el.updateComplete;
  return { el, adapter };
}

const $ = (el: MiresViewer, selector: string) => el.shadowRoot!.querySelector<HTMLElement>(selector);
const $$ = (el: MiresViewer, selector: string) => [...el.shadowRoot!.querySelectorAll<HTMLElement>(selector)];
const metadataFetches = () => fetched.filter((f) => f.url.endsWith("/metadata")).map((f) => f.url);

afterEach(() => {
  document.body.innerHTML = "";
  localStorage.clear();
  vi.unstubAllGlobals();
});

describe("JSON series list", () => {
  it("opens the first opened series and fuses the other opened ones onto it", async () => {
    const { el } = await mount((v) => (v.entries = ENTRIES));

    expect(el.volumeState?.layers.map((l) => l.seriesUid)).toEqual(["ct", "pet"]);
    expect($$(el, ".ser.shown").map((r) => r.dataset.seriesUid)).toEqual(["ct", "pet"]);
  });

  it("lists the Related Series from the list itself, without fetching their metadata", async () => {
    const { el } = await mount((v) => (v.entries = ENTRIES));

    expect($$(el, ".ser").map((r) => r.dataset.seriesUid)).toEqual(["ct", "pet", "mr"]);
    expect($(el, '.ser[data-series-uid="mr"]')!.textContent).toContain("Brain MR (2025)");
    expect(metadataFetches().some((u) => u.includes("/series/mr/"))).toBe(false);
  });

  it("fetches a series of another study under that study", async () => {
    const { el } = await mount((v) => (v.entries = ENTRIES));

    $(el, '.ser[data-series-uid="mr"]')!.dispatchEvent(new Event("dragstart", { bubbles: true, composed: true }));
    await el.updateComplete;
    const target = $(el, '.drop-zone[data-zone="replace"]')!;
    target.dispatchEvent(new Event("drop", { bubbles: true, cancelable: true, composed: true }));
    await vi.waitFor(() => expect(el.fusionBusy).toBe(false));

    expect(metadataFetches()).toContain("/api/v1/dicom/studies/study-2/series/mr/metadata");
    expect(metadataFetches()).toContain("/api/v1/dicom/studies/study-1/series/ct/metadata");
  });

  it("reads the list from the page's JSON script named by series-list", async () => {
    const script = document.createElement("script");
    script.type = "application/json";
    script.id = "viewer-series";
    script.textContent = JSON.stringify([entry("ct", "study-1", true, "CT", "Chest CT")]);
    document.body.append(script);

    const { el } = await mount((v) => v.setAttribute("series-list", "viewer-series"));

    expect($$(el, ".ser").map((r) => r.dataset.seriesUid)).toEqual(["ct"]);
  });

  it("fails with a reason when nothing is to be opened", async () => {
    stubFetch();
    const el = document.createElement("mires-viewer") as MiresViewer;
    el.adapterFactory = async () => new StubAdapter();
    el.entries = [entry("mr", "study-2", false)];
    document.body.append(el);

    await vi.waitFor(() => expect(el.getAttribute("state")).toBe("error"));
  });

  it("sends the page's Viewer Session with its requests", async () => {
    await mount((v) => {
      v.entries = ENTRIES;
      v.setAttribute("viewer-session", "page-session-1");
    });

    expect(fetched.length).toBeGreaterThan(0);
    expect(fetched.every((f) => f.headers[VIEWER_SESSION_HEADER] === "page-session-1")).toBe(true);
  });
});
