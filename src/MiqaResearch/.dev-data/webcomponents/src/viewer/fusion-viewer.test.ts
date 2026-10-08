// #284 fusion on <mires-viewer>: related series in the list, drop zones (top half fuses, bottom
// half replaces), refusals with the reason, per-layer window / colormap / opacity curve, SUV warning.
// Seam: the element with the stub adapter; /metadata served by a stubbed fetch per series UID.
import { afterEach, describe, expect, it, vi } from "vitest";

import { StubAdapter } from "./adapter/stub.ts";
import { MiresViewer } from "./mires-viewer.ts";
import type { DicomJsonInstance } from "./series.ts";
import { petInstance, volumeInstances } from "./test-fixtures.ts";

const CT = volumeInstances(8, { description: "Chest CT" });
const PET = volumeInstances(8, { modality: "PT", description: "PET AC", extra: petInstance() });
const PET_NO_WEIGHT = volumeInstances(8, { modality: "PT", description: "PET no weight", extra: petInstance({ "00101030": undefined }) });
const MR_OTHER_FOR = volumeInstances(8, { modality: "MR", description: "Brain MR", frameOfReference: "2.25.99" });

const METADATA: Record<string, DicomJsonInstance[]> = { ct: CT, pet: PET, petnw: PET_NO_WEIGHT, mr: MR_OTHER_FOR };

async function mount({ related = "pet petnw mr", budget, max3d = 2048 }: { related?: string; budget?: number; max3d?: number } = {}) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      const uid = /series\/([^/]+)\/metadata/.exec(url)![1];
      return new Response(JSON.stringify(METADATA[uid]));
    }),
  );
  const adapter = new StubAdapter();
  adapter.gpu = { max3dTextureSize: max3d, maxTextureSize: 16384 };
  const el = document.createElement("mires-viewer") as MiresViewer;
  el.adapterFactory = async () => adapter;
  el.setAttribute("study-uid", "2.25.1");
  el.setAttribute("series-uid", "ct");
  el.setAttribute("related-series", related);
  el.canAnnotate = true;
  if (budget) (el.budget as unknown as { budget: number }).budget = budget;
  document.body.append(el);
  await vi.waitFor(() => expect(el.getAttribute("state")).toBe("ready"));
  await vi.waitFor(() => expect($$(el, ".ser").length).toBe(1 + related.split(" ").filter(Boolean).length));
  await el.updateComplete;
  return { el, adapter };
}

const $ = (el: MiresViewer, selector: string) => el.shadowRoot!.querySelector<HTMLElement>(selector);
const $$ = (el: MiresViewer, selector: string) => [...el.shadowRoot!.querySelectorAll<HTMLElement>(selector)];

async function settle(el: MiresViewer) {
  await vi.waitFor(() => expect(el.layoutBusy).toBe(false));
  await el.updateComplete;
}

/** Drag a series row onto the big view's top (fuse) or bottom (replace) half. */
async function drop(el: MiresViewer, uid: string, zone: "fuse" | "replace") {
  $(el, `.ser[data-series-uid="${uid}"]`)!.dispatchEvent(new Event("dragstart", { bubbles: true, composed: true }));
  await el.updateComplete;
  const target = $(el, `.drop-zone[data-zone="${zone}"]`)!;
  target.dispatchEvent(new Event("dragover", { bubbles: true, cancelable: true, composed: true }));
  target.dispatchEvent(new Event("drop", { bubbles: true, cancelable: true, composed: true }));
  await vi.waitFor(() => expect(el.fusionBusy).toBe(false));
  await settle(el);
}

async function press(el: MiresViewer, key: string) {
  el.dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true, composed: true }));
  await el.updateComplete;
}

const layers = (el: MiresViewer) => el.volumeState?.layers ?? [];

afterEach(() => {
  document.body.innerHTML = "";
  localStorage.clear();
  vi.unstubAllGlobals();
});

describe("series list", () => {
  it("lists the related series, only the shown one marked", async () => {
    const { el } = await mount();

    expect($$(el, ".ser").map((r) => r.dataset.seriesUid)).toEqual(["ct", "pet", "petnw", "mr"]);
    expect($$(el, ".ser.shown").map((r) => r.dataset.seriesUid)).toEqual(["ct"]);
    expect($(el, '.ser[data-series-uid="pet"]')!.getAttribute("draggable")).toBe("true");
  });

  it("shows the drop zones only while a series is dragged", async () => {
    const { el } = await mount();
    expect($(el, ".drop-zone")).toBeNull();

    $(el, '.ser[data-series-uid="pet"]')!.dispatchEvent(new Event("dragstart", { bubbles: true, composed: true }));
    await el.updateComplete;
    expect($$(el, ".drop-zone").map((z) => z.dataset.zone)).toEqual(["fuse", "replace"]);

    $(el, '.ser[data-series-uid="pet"]')!.dispatchEvent(new Event("dragend", { bubbles: true, composed: true }));
    await el.updateComplete;
    expect($(el, ".drop-zone")).toBeNull();
  });
});

describe("drop on the top half: fuse", () => {
  it("fuses a PET with the same Frame of Reference into three views, selected, in SUV with the default curve", async () => {
    const { el, adapter } = await mount();

    await drop(el, "pet", "fuse");

    const state = el.volumeState!;
    expect(state.views).toHaveLength(3);
    expect(state.layers.map((l) => l.seriesUid)).toEqual(["ct", "pet"]);
    expect(state.selectedLayer).toBe("pet");
    expect(state.layers[1]).toMatchObject({
      colormap: "hsv",
      voi: { lower: 0, upper: 5 },
      curve: [
        { value: 0, opacity: 0 },
        { value: 2, opacity: 0 },
        { value: 4, opacity: 1 },
      ],
      suv: { applied: true },
    });
    expect($$(el, ".ser.shown").map((r) => r.dataset.seriesUid)).toEqual(["ct", "pet"]);
    // CT volume + labelmap reserve + PET volume (float, 4 B), all 64 × 64 × 8.
    expect(el.budget.used()).toBe(64 * 64 * 8 * (2 + 1 + 4));
    expect(adapter.volumes).toHaveLength(1);
    expect($(el, ".refusal")).toBeNull();
  });

  it("refuses a different Frame of Reference with the reason, and changes nothing", async () => {
    const { el, adapter } = await mount();

    await drop(el, "mr", "fuse");

    expect($(el, ".refusal")!.textContent).toContain("different Frame of Reference");
    expect(adapter.volumes).toHaveLength(0);
    expect(el.budget.used()).toBe(0);
  });

  it("refuses an overlay over the budget, keeping the views", async () => {
    // CT volume + reserve = 96 KiB; the PET's 128 KiB doesn't fit in 200 KiB.
    const { el } = await mount({ budget: 200 * 1024 });
    $(el, '[data-layout="three"]')!.click();
    await settle(el);

    await drop(el, "pet", "fuse");

    expect($(el, ".refusal")!.textContent).toContain("Can't fuse: the overlay needs");
    expect(el.volumeState!.layers.map((l) => l.seriesUid)).toEqual(["ct"]);
    expect(el.budget.used()).toBe(64 * 64 * 8 * 3);
  });

  it("refuses from the stack without opening anything when base and overlay don't fit together", async () => {
    const { el, adapter } = await mount({ budget: 200 * 1024 });

    await drop(el, "pet", "fuse");

    expect($(el, ".refusal")!.textContent).toContain("Can't fuse: the overlay needs");
    expect(adapter.volumes).toHaveLength(0);
    expect(el.budget.used()).toBe(0);
  });

  it("frees a removed overlay's budget and cache; the stack keeps cached overlays counted", async () => {
    const { el, adapter } = await mount();
    await drop(el, "pet", "fuse");

    $(el, '[data-remove-layer="pet"]')!.click();
    await settle(el);
    expect(layers(el).map((l) => l.seriesUid)).toEqual(["ct"]);
    expect(adapter.evicted).toEqual(["pet"]);
    expect(el.budget.used()).toBe(64 * 64 * 8 * 3);

    // Closing the volume view leaves CS3D's cache (and so the budget) as is.
    await drop(el, "pet", "fuse");
    $(el, '[data-layout="stack"]')!.click();
    await settle(el);
    expect(el.budget.used()).toBe(64 * 64 * 8 * 7);
  });

  it("removes an overlay CS3D's cache refuses while streaming, and says so", async () => {
    const { el, adapter } = await mount();
    await drop(el, "pet", "fuse");

    adapter.volumes[0].overlayTooLarge("pet");
    await settle(el);

    expect(layers(el).map((l) => l.seriesUid)).toEqual(["ct"]);
    expect($(el, ".refusal")!.textContent).toContain("image cache is full");
    expect(el.budget.used()).toBe(64 * 64 * 8 * 3);
  });
});

describe("selected layer", () => {
  it("presets and W/L act on the selected overlay only", async () => {
    const { el } = await mount();
    await drop(el, "pet", "fuse");
    const baseVoi = layers(el)[0].voi;

    await press(el, "8"); // SUV 0–10, a PET preset

    expect(layers(el)[1].voi).toEqual({ lower: 0, upper: 10 });
    expect(layers(el)[0].voi).toEqual(baseVoi);
    expect($$(el, "[data-preset]").map((b) => b.dataset.preset)).toEqual(["dicom", "suv5", "suv10"]);

    $(el, '[data-layer="ct"]')!.click();
    await el.updateComplete;
    await press(el, "1"); // CT soft tissue

    expect(layers(el)[0].voi).toEqual({ lower: -160, upper: 239 });
    expect(layers(el)[1].voi).toEqual({ lower: 0, upper: 10 });
  });

  it("sets the colormap, opacity multiplier and curve breakpoints of the selected layer", async () => {
    const { el } = await mount();
    await drop(el, "pet", "fuse");

    const select = $(el, "select[data-colormap]") as HTMLSelectElement;
    select.value = "jet";
    select.dispatchEvent(new Event("change"));
    const opacity = $(el, "input[data-opacity]") as HTMLInputElement;
    opacity.value = "40";
    opacity.dispatchEvent(new Event("input"));
    const value = $(el, 'input[data-curve-value="1"]') as HTMLInputElement;
    value.value = "3";
    value.dispatchEvent(new Event("change"));
    await el.updateComplete;

    expect(layers(el)[1]).toMatchObject({
      colormap: "jet",
      opacity: 0.4,
      curve: [
        { value: 0, opacity: 0 },
        { value: 3, opacity: 0 },
        { value: 4, opacity: 1 },
      ],
    });
  });

  it("offers a colormap for the base in reduced 3D", async () => {
    // GPU 3D textures of 32 px: the 64 px CT only opens reduced (view only).
    const { el } = await mount({ max3d: 32 });
    $(el, '[data-layout="reduced"]')!.click();
    await settle(el);

    expect(el.volumeState?.layers).toHaveLength(1);
    const select = $(el, "select[data-colormap]") as HTMLSelectElement;
    select.value = "Inferno (matplotlib)";
    select.dispatchEvent(new Event("change"));
    expect(layers(el)[0].colormap).toBe("Inferno (matplotlib)");
  });
});

describe("SUV", () => {
  it("warns when SUV scaling wasn't applied to a fused PET", async () => {
    const { el } = await mount();

    await drop(el, "petnw", "fuse");

    const warning = $(el, '.suv-warning[data-series-uid="petnw"]')!.textContent!;
    expect(warning).toContain("Bq/ml, not SUV");
    expect(warning).toContain("missing PatientWeight");
    // A PET in Bq/ml gets no SUV curve or window.
    expect(layers(el)[1]).toMatchObject({ curve: [], opacity: 0.5, voi: undefined });
  });

  it("shows no warning for a PET in SUV", async () => {
    const { el } = await mount();

    await drop(el, "pet", "fuse");

    expect($(el, ".suv-warning")).toBeNull();
  });
});

describe("drop on the bottom half: replace", () => {
  it("shows the dropped series instead, keeping three views, and frees the old series' budget", async () => {
    const { el, adapter } = await mount();
    $(el, '[data-layout="three"]')!.click();
    await settle(el);

    await drop(el, "mr", "replace");

    expect(el.seriesUid).toBe("mr");
    expect(el.volumeState!.views).toHaveLength(3);
    expect(layers(el).map((l) => l.seriesUid)).toEqual(["mr"]);
    expect($$(el, ".ser.shown").map((r) => r.dataset.seriesUid)).toEqual(["mr"]);
    expect(el.budget.open().map((e) => e.series)).toEqual(["mr", "mr"]);
    expect(adapter.evicted).toEqual(["ct"]);
  });

  it("replaces a stack with a stack", async () => {
    const { el, adapter } = await mount();

    await drop(el, "pet", "replace");

    expect(adapter.opened.map((o) => o.series.ref.seriesUid)).toEqual(["ct", "pet"]);
    expect(el.stackState).toBeDefined();
    expect($$(el, ".ser.shown").map((r) => r.dataset.seriesUid)).toEqual(["pet"]);
  });

  it("says why when the series is already shown", async () => {
    const { el } = await mount();

    await drop(el, "ct", "replace");

    expect($(el, ".refusal")!.textContent).toContain("is already shown");
  });

  it("warns in the stack when the PET shown has no SUV", async () => {
    const { el } = await mount();

    await drop(el, "petnw", "replace");

    expect($(el, ".suv-warning")!.textContent).toContain("missing PatientWeight");
  });
});
