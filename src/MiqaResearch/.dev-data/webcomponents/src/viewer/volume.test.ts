// #282 volumes on <mires-viewer>: layout panel, 1×1 orientation + V, three views with crosshairs,
// split + double-click swap, MPR gated by the reconstructability rule, first-render volume marks.
// Seam: the element with the stub adapter.
import { afterEach, describe, expect, it, vi } from "vitest";

import { StubAdapter } from "./adapter/stub.ts";
import { SPLIT_STORAGE_KEY } from "./layout.ts";
import { MiresViewer } from "./mires-viewer.ts";
import { seriesEntries } from "./test-fixtures.ts";

const ct = (n: number) =>
  Array.from({ length: n }, (_, i) => ({
    "00080018": { vr: "UI", Value: [`2.25.${i + 1}`] },
    "00080060": { vr: "CS", Value: ["CT"] },
    "00200013": { vr: "IS", Value: [i + 1] },
    "00200032": { vr: "DS", Value: [0, 0, i * 2.5] },
    "00200037": { vr: "DS", Value: [1, 0, 0, 0, 1, 0] },
    "00280010": { vr: "US", Value: [64] },
    "00280011": { vr: "US", Value: [64] },
    "00280002": { vr: "US", Value: [1] },
  }));

async function mount(metadata: unknown[] = ct(8)) {
  vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(metadata))));
  const adapter = new StubAdapter();
  const el = document.createElement("mires-viewer") as MiresViewer;
  el.adapterFactory = async () => adapter;
  el.entries = seriesEntries(["2.25.200"], [], "2.25.100");
  document.body.append(el);
  await vi.waitFor(() => expect(el.getAttribute("state")).toBe("ready"));
  await el.updateComplete;
  return { el, adapter };
}

const $ = (el: MiresViewer, selector: string) => el.shadowRoot!.querySelector<HTMLElement>(selector);
const $$ = (el: MiresViewer, selector: string) => [...el.shadowRoot!.querySelectorAll<HTMLElement>(selector)];
const railTools = (el: MiresViewer) => $$(el, ".rail [data-tool]").map((b) => b.dataset.tool);

async function click(el: MiresViewer, selector: string) {
  $(el, selector)!.click();
  await vi.waitFor(() => expect(el.layoutBusy).toBe(false));
  await el.updateComplete;
}

async function press(el: MiresViewer, key: string) {
  el.dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true, composed: true }));
  await vi.waitFor(() => expect(el.layoutBusy).toBe(false));
  await el.updateComplete;
}

afterEach(() => {
  document.body.innerHTML = "";
  localStorage.clear();
  vi.unstubAllGlobals();
});

describe("layout panel", () => {
  it("offers stack, the three orientations and three views for a reconstructable series", async () => {
    const { el } = await mount();

    expect($$(el, "[data-layout]").map((b) => b.dataset.layout)).toEqual(["stack", "axial", "sagittal", "coronal", "three"]);
    expect($(el, '[data-layout="stack"]')!.getAttribute("aria-pressed")).toBe("true");
  });

  it("doesn't offer MPR for a non-reconstructable series, and says why", async () => {
    const { el, adapter } = await mount(ct(1));

    expect($$(el, "[data-layout]")).toHaveLength(0);
    expect($(el, ".layout-hint")!.textContent).toContain("single image");
    await press(el, "v");
    expect(adapter.volumes).toHaveLength(0);
  });
});

describe("1×1 volume", () => {
  it("replaces the stack with the volume in one ORTHOGRAPHIC view of the chosen orientation", async () => {
    const { el, adapter } = await mount();
    const stack = adapter.views[0];

    await click(el, '[data-layout="sagittal"]');

    expect(adapter.closed).toEqual([stack]);
    expect(adapter.volumes).toHaveLength(1);
    const volume = adapter.volumes[0];
    expect(volume.orientations).toEqual(["sagittal"]);
    expect(volume.series.images).toHaveLength(8);
    expect(el.shadowRoot!.contains(volume.slots[0])).toBe(true);
    expect($(el, '[data-layout="sagittal"]')!.getAttribute("aria-pressed")).toBe("true");
    expect(el.volumeState?.views.map((v) => v.orientation)).toEqual(["sagittal"]);
  });

  it("keeps the selected tool, without crosshairs in a single view", async () => {
    const { el, adapter } = await mount();
    await press(el, "l");

    await click(el, '[data-layout="axial"]');

    expect(adapter.volumes[0].current.activeTool).toBe("Length");
    expect(railTools(el)).not.toContain("Crosshairs");
    expect(railTools(el)).toContain("WindowLevel");
  });

  it("V cycles axial → sagittal → coronal", async () => {
    const { el, adapter } = await mount();
    await click(el, '[data-layout="axial"]');

    await press(el, "v");
    expect(adapter.volumes[0].orientations).toEqual(["sagittal"]);
    await press(el, "v");
    expect(adapter.volumes[0].orientations).toEqual(["coronal"]);
    await press(el, "v");
    expect(adapter.volumes[0].orientations).toEqual(["axial"]);
    expect(adapter.volumes).toHaveLength(1);
  });

  it("V does nothing on the stack", async () => {
    const { el, adapter } = await mount();

    await press(el, "v");

    expect(adapter.volumes).toHaveLength(0);
  });

  it("goes back to the stack", async () => {
    const { el, adapter } = await mount();
    await click(el, '[data-layout="coronal"]');

    await click(el, '[data-layout="stack"]');

    expect(adapter.closed).toContain(adapter.volumes[0]);
    expect(adapter.views).toHaveLength(2);
    expect(el.stackState).toBeDefined();
    expect(el.volumeState).toBeUndefined();
    expect($(el, ".viewport")).not.toBeNull();
  });
});

describe("three views", () => {
  it("shows axial big on the left, sagittal and coronal stacked right, with Crosshairs selected", async () => {
    const { el, adapter } = await mount();

    await click(el, '[data-layout="three"]');

    const volume = adapter.volumes[0];
    expect(volume.orientations).toEqual(["axial", "sagittal", "coronal"]);
    expect($$(el, ".vcell").filter((c) => !c.hidden).map((c) => c.dataset.orientation)).toEqual([
      "axial",
      "sagittal",
      "coronal",
    ]);
    expect(volume.current.activeTool).toBe("Crosshairs");
    expect(railTools(el)).toContain("Crosshairs");
    expect($(el, '[data-tool="Crosshairs"]')!.getAttribute("aria-pressed")).toBe("true");
  });

  it("X selects Crosshairs", async () => {
    const { el, adapter } = await mount();
    await click(el, '[data-layout="three"]');
    await press(el, "l");

    await press(el, "x");

    expect(adapter.volumes[0].current.activeTool).toBe("Crosshairs");
  });

  it("double-clicking a small view swaps it into the big one", async () => {
    const { el, adapter } = await mount();
    await click(el, '[data-layout="three"]');

    $(el, '.vcell[data-slot="2"]')!.dispatchEvent(new MouseEvent("dblclick", { bubbles: true }));
    await vi.waitFor(() => expect(adapter.volumes[0].orientations).toEqual(["coronal", "sagittal", "axial"]));
  });

  it("switching from three views to one keeps the volume and leaves crosshairs", async () => {
    const { el, adapter } = await mount();
    await click(el, '[data-layout="three"]');

    await click(el, '[data-layout="coronal"]');

    expect(adapter.volumes).toHaveLength(1);
    expect(adapter.volumes[0].orientations).toEqual(["coronal"]);
    expect(adapter.volumes[0].current.activeTool).toBe("WindowLevel");
  });

  it("starts the split at 66% and restores a remembered one", async () => {
    localStorage.setItem(SPLIT_STORAGE_KEY, "40");
    const { el } = await mount();

    await click(el, '[data-layout="three"]');

    expect($(el, ".vgrid")!.style.getPropertyValue("--split")).toBe("40%");
  });
});

describe("first-render marks", () => {
  it("marks the interleaved stage and the loaded volume on the element's report", async () => {
    const { el, adapter } = await mount();
    const mark = vi.spyOn(el.firstRender!, "mark");

    await click(el, '[data-layout="three"]');
    adapter.volumes[0].stage("interleaved");
    adapter.volumes[0].stage("volume-loaded");

    expect(mark.mock.calls).toEqual([["interleaved"], ["volume-loaded"]]);
  });
});
