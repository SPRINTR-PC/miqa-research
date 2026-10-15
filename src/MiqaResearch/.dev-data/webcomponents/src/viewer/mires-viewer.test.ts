import { afterEach, describe, expect, it, vi } from "vitest";

import { StubAdapter } from "./adapter/stub.ts";
import { MiresViewer } from "./mires-viewer.ts";
import { seriesEntries } from "./test-fixtures.ts";

const SERIES_METADATA = [1, 2, 3].map((n) => ({
  "00080018": { vr: "UI", Value: [`2.25.${n}`] },
  "00200013": { vr: "IS", Value: [n] },
}));

function serve(body: unknown, status = 200) {
  vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(body), { status })));
}

async function mount(adapter: StubAdapter): Promise<MiresViewer> {
  const el = document.createElement("mires-viewer") as MiresViewer;
  el.adapterFactory = async () => adapter;
  el.setAttribute("wado-root", "/api/v1/dicom");
  el.entries = seriesEntries(["2.25.200"], [], "2.25.100");
  document.body.append(el);
  await vi.waitFor(() => expect(el.getAttribute("state")).toMatch(/ready|error/));
  await el.updateComplete;
  return el;
}

const text = (el: MiresViewer, selector: string) => el.shadowRoot!.querySelector(selector)?.textContent?.trim();

afterEach(() => {
  document.body.innerHTML = "";
  vi.unstubAllGlobals();
});

describe("<mires-viewer>", () => {
  it("opens the requested series as a stack in a viewport inside its shadow root", async () => {
    serve(SERIES_METADATA);
    const adapter = new StubAdapter();

    const el = await mount(adapter);

    expect(el.getAttribute("state")).toBe("ready");
    expect(adapter.opened).toHaveLength(1);
    const { element, series } = adapter.opened[0];
    expect(el.shadowRoot!.contains(element)).toBe(true);
    expect(series.images.map((i) => i.imageId)).toEqual(
      [1, 2, 3].map((n) => `wadors:/api/v1/dicom/studies/2.25.100/series/2.25.200/instances/2.25.${n}/frames/1`),
    );
  });

  it("shows the image position and window, and follows changes from the view", async () => {
    serve(SERIES_METADATA);
    const adapter = new StubAdapter();
    const el = await mount(adapter);
    expect(text(el, ".overlay")).toContain("1 / 3");

    adapter.views[0].scrollTo(2);
    // W 400 / C 40 as a linear VOI range (DICOM PS3.3 C.11.2.1.2): [C - 0.5 - (W-1)/2, C - 0.5 + (W-1)/2]
    adapter.views[0].setVoi({ lower: -160, upper: 239 });
    await el.updateComplete;

    expect(text(el, ".overlay")).toContain("3 / 3");
    expect(text(el, ".overlay")).toContain("W 400 L 40");
  });

  it("reports a series it may not see as an error, without opening a view", async () => {
    serve({ detail: "Not Found" }, 404);
    const adapter = new StubAdapter();

    const el = await mount(adapter);

    expect(el.getAttribute("state")).toBe("error");
    expect(text(el, "[role=alert]")).toContain("404");
    expect(adapter.opened).toHaveLength(0);
  });

  it("reports a rendering failure as an error", async () => {
    serve(SERIES_METADATA);
    const adapter = new StubAdapter();
    adapter.failWith = new Error("WebGL unavailable");

    const el = await mount(adapter);

    expect(el.getAttribute("state")).toBe("error");
    expect(text(el, "[role=alert]")).toContain("WebGL unavailable");
  });

  it("releases the adapter when removed from the page", async () => {
    serve(SERIES_METADATA);
    const adapter = new StubAdapter();
    const el = await mount(adapter);

    el.remove();

    expect(adapter.destroyed).toBe(true);
  });

  it("sends the first-render beacon, without UIDs, when the view closes", async () => {
    serve(SERIES_METADATA);
    const el = await mount(new StubAdapter());

    el.remove();

    const fetchMock = vi.mocked(fetch);
    const beacon = fetchMock.mock.calls.find(([url]) => url === "/api/v1/viewer/first-render");
    expect(beacon).toBeDefined();
    const body = JSON.parse(String(beacon![1]!.body));
    expect(body).toEqual({ first_image_ms: expect.any(Number), slices: 3 });
  });
});
