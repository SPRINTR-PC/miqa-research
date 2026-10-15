// <mires-viewer> on a whole-slide (WSI) series (#285), against the stub adapter.
import { afterEach, describe, expect, it, vi } from "vitest";

import { StubAdapter } from "./adapter/stub.ts";
import { MiresViewer } from "./mires-viewer.ts";
import { seriesEntries } from "./test-fixtures.ts";

const WSI_SOP_CLASS = "1.2.840.10008.5.1.4.1.1.77.1.6";

// Two pyramid levels: 4 tiles and 1 tile.
const WSI_METADATA = [
  { sop: "2.25.1", frames: 4 },
  { sop: "2.25.2", frames: 1 },
].map(({ sop, frames }) => ({
  "00080016": { vr: "UI", Value: [WSI_SOP_CLASS] },
  "00080018": { vr: "UI", Value: [sop] },
  "00080060": { vr: "CS", Value: ["SM"] },
  "00280008": { vr: "IS", Value: [frames] },
}));

async function mount(adapter: StubAdapter, canAnnotate = true): Promise<MiresViewer> {
  vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(WSI_METADATA))));
  const el = document.createElement("mires-viewer") as MiresViewer;
  el.adapterFactory = async () => adapter;
  el.entries = seriesEntries(["2.25.200"], [], "2.25.100");
  el.toggleAttribute("can-annotate", canAnnotate);
  document.body.append(el);
  await vi.waitFor(() => expect(el.getAttribute("state")).toMatch(/ready|error/));
  await el.updateComplete;
  return el;
}

const railTools = (el: MiresViewer) =>
  [...el.shadowRoot!.querySelectorAll<HTMLElement>(".rail [data-tool]")].map((b) => b.dataset.tool);

afterEach(() => {
  document.body.innerHTML = "";
  vi.unstubAllGlobals();
});

describe("<mires-viewer> on a WSI series", () => {
  it("opens it as a whole slide, not a stack, in a viewport inside its shadow root", async () => {
    const adapter = new StubAdapter();

    const el = await mount(adapter);

    expect(el.getAttribute("state")).toBe("ready");
    expect(adapter.opened).toHaveLength(0);
    expect(adapter.openedWsi).toHaveLength(1);
    const { element, series } = adapter.openedWsi[0];
    expect(el.shadowRoot!.contains(element)).toBe(true);
    expect(series.images).toHaveLength(5);
  });

  it("offers the WSI tool set, with Pan on the left button", async () => {
    const adapter = new StubAdapter();

    const el = await mount(adapter);

    expect(railTools(el)).toEqual([
      "Pan",
      "Zoom",
      "Length",
      "RectangleROI",
      "EllipticalROI",
      "PlanarFreehandROI",
      "ArrowAnnotate",
    ]);
    expect(adapter.views[0].state().activeTool).toBe("Pan");
  });

  it("selects WSI tools by key and ignores tools outside the WSI set", async () => {
    const adapter = new StubAdapter();
    const el = await mount(adapter);

    el.dispatchEvent(new KeyboardEvent("keydown", { key: "l" }));
    expect(adapter.views[0].state().activeTool).toBe("Length");
    el.dispatchEvent(new KeyboardEvent("keydown", { key: "w" }));

    expect(adapter.views[0].state().activeTool).toBe("Length");
  });

  it("shows no image position overlay (a slide has one image)", async () => {
    const el = await mount(new StubAdapter());

    expect(el.shadowRoot!.querySelector(".overlay")).toBeNull();
  });
});
