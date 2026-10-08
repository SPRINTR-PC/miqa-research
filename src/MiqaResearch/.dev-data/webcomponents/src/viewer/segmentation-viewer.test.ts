// #286 segmentation on <mires-viewer>: a labelmap made on first use of a segment tool (through the
// size guard), shown in every view, the segments panel and the threshold form.
// Seam: the element with the stub adapter.
import { afterEach, describe, expect, it, vi } from "vitest";

import { StubAdapter } from "./adapter/stub.ts";
import { MiresViewer } from "./mires-viewer.ts";
import { BUDGET_BYTES, TOO_LARGE_MESSAGE } from "./size-guard.ts";

const ct = (n: number, size = 64) =>
  Array.from({ length: n }, (_, i) => ({
    "00080018": { vr: "UI", Value: [`2.25.${i + 1}`] },
    "00080060": { vr: "CS", Value: ["CT"] },
    "00200013": { vr: "IS", Value: [i + 1] },
    "00200032": { vr: "DS", Value: [0, 0, i * 2.5] },
    "00200037": { vr: "DS", Value: [1, 0, 0, 0, 1, 0] },
    "00280010": { vr: "US", Value: [size] },
    "00280011": { vr: "US", Value: [size] },
    "00280002": { vr: "US", Value: [1] },
    "00280100": { vr: "US", Value: [16] },
  }));

async function mount({ canAnnotate = true } = {}) {
  vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(ct(8)))));
  const adapter = new StubAdapter();
  const el = document.createElement("mires-viewer") as MiresViewer;
  el.adapterFactory = async () => adapter;
  el.setAttribute("study-uid", "2.25.100");
  el.setAttribute("series-uid", "2.25.200");
  el.canAnnotate = canAnnotate;
  document.body.append(el);
  await vi.waitFor(() => expect(el.getAttribute("state")).toBe("ready"));
  await el.updateComplete;
  return { el, adapter };
}

const $ = (el: MiresViewer, selector: string) => el.shadowRoot!.querySelector<HTMLElement>(selector);
const $$ = (el: MiresViewer, selector: string) => [...el.shadowRoot!.querySelectorAll<HTMLElement>(selector)];
const LABELMAP_BYTES = 64 * 64 * 8;

async function press(el: MiresViewer, key: string) {
  el.dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true, composed: true }));
  await vi.waitFor(() => expect(el.segmentationBusy).toBe(false));
  await el.updateComplete;
}

async function click(el: MiresViewer, selector: string) {
  $(el, selector)!.click();
  await vi.waitFor(() => expect(el.layoutBusy || el.segmentationBusy).toBe(false));
  await el.updateComplete;
}

async function change(el: MiresViewer, selector: string, value: string) {
  const input = $(el, selector) as HTMLInputElement;
  input.value = value;
  input.dispatchEvent(new Event("change", { bubbles: true }));
  await el.updateComplete;
}

afterEach(() => {
  document.body.innerHTML = "";
  vi.unstubAllGlobals();
});

describe("the labelmap", () => {
  it("is made on the base series' grid when a segment tool is first selected, and shown in the stack", async () => {
    const { el, adapter } = await mount();
    expect(adapter.segmentations).toHaveLength(0);

    await press(el, "g");

    expect(adapter.segmentations).toHaveLength(1);
    const seg = adapter.segmentations[0];
    expect(seg.series.ref.seriesUid).toBe("2.25.200");
    expect(seg.shownIn).toEqual([adapter.views[0]]);
    expect(adapter.views[0].state().activeTool).toBe("Brush");
    expect(el.budget.used()).toBe(LABELMAP_BYTES);

    await press(el, "d");

    expect(adapter.segmentations).toHaveLength(1);
  });

  it("over budget: the refusal is shown, no labelmap is made and the tool stays", async () => {
    const { el, adapter } = await mount();
    el.budget.reserve([{ id: "other", series: "2.25.999", kind: "volume", bytes: BUDGET_BYTES - 1000 }]);

    await press(el, "g");

    expect($(el, ".refusal")!.textContent).toContain("Can't add a segmentation");
    expect($(el, ".refusal")!.textContent).toContain("Save and close the other Segmentation first.");
    expect(adapter.segmentations).toHaveLength(0);
    expect(adapter.views[0].state().activeTool).toBe("WindowLevel");
  });

  it("a CS3D cache error frees the budget and says it is too large", async () => {
    const { el, adapter } = await mount();
    adapter.segmentationFailWith = new Error("Derived volume is not cacheable");

    await press(el, "g");

    expect($(el, ".refusal")!.textContent).toContain(TOO_LARGE_MESSAGE);
    expect(el.budget.used()).toBe(0);
    expect(adapter.views[0].state().activeTool).toBe("WindowLevel");
  });

  it("follows the views: shown in the volume after a switch, and kept", async () => {
    const { el, adapter } = await mount();
    await press(el, "g");

    await click(el, '[data-layout="axial"]');

    const seg = adapter.segmentations[0];
    expect(adapter.segmentations).toHaveLength(1);
    expect(seg.shownIn.at(-1)).toBe(adapter.volumes[0]);
    expect(adapter.volumes[0].state().activeTool).toBe("Brush");
  });

  it("is closed and its budget freed when the viewer goes away", async () => {
    const { el, adapter } = await mount();
    await press(el, "g");

    el.remove();

    expect(adapter.segmentations[0].closed).toBe(true);
    expect(el.budget.used()).toBe(0);
  });
});

describe("the segments panel", () => {
  it("is not offered to view-only roles", async () => {
    const { el } = await mount({ canAnnotate: false });

    expect($(el, ".segments")).toBeNull();
  });

  it("starts a segmentation on request", async () => {
    const { el, adapter } = await mount();

    await click(el, '[data-action="new-segmentation"]');

    expect(adapter.segmentations).toHaveLength(1);
    expect($$(el, ".segments [data-segment]").map((r) => (r.querySelector("input[type=text]") as HTMLInputElement).value)).toEqual([
      "Segment 1",
    ]);
  });

  it("adds, renames, recolours and activates segments", async () => {
    const { el, adapter } = await mount();
    await press(el, "g");

    await click(el, '[data-action="add-segment"]');
    await change(el, '[data-segment="1"] input[type=text]', "Tumour");
    await change(el, '[data-segment="1"] input[type=color]', "#102030");
    await click(el, '[data-segment="1"] [data-action="activate"]');

    const state = adapter.segmentations[0].state();
    expect(state.segments.map((s) => s.label)).toEqual(["Tumour", "Segment 2"]);
    expect(state.segments[0].color).toEqual([16, 32, 48]);
    expect(state.active).toBe(1);
    expect($(el, '[data-segment="1"] [data-action="activate"]')!.getAttribute("aria-pressed")).toBe("true");
  });

  it("threshold: Run fills the active segment of the base series within the range, once a rectangle is drawn", async () => {
    const { el, adapter } = await mount();
    await press(el, "m");
    const seg = adapter.segmentations[0];
    expect(($(el, '[data-action="threshold"]') as HTMLButtonElement).disabled).toBe(true);
    expect(($(el, "input[name=lower]") as HTMLInputElement).value).toBe("300");

    seg.thresholdResult = 42;
    seg.emit({ thresholdRectangles: 1 });
    await el.updateComplete;
    await change(el, "input[name=lower]", "-100");
    await change(el, "input[name=upper]", "100");
    await change(el, "input[name=slices]", "2");
    await click(el, '[data-action="threshold"]');

    expect(seg.thresholds).toEqual([{ range: { lower: -100, upper: 100 }, options: { slices: 2, sourceSeriesUid: "2.25.200" } }]);
    expect($(el, ".segments .threshold-result")!.textContent).toContain("42");
  });
});
