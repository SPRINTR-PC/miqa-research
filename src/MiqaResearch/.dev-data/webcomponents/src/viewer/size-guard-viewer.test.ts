// #283 size guard on <mires-viewer>: banner + full-resolution stack for a series too big for 3D,
// reduced 3D (view only), budget reserved per volume, refusals and CS3D cache errors.
// Seam: the element with the stub adapter (GPU limits stubbed there).
import { afterEach, describe, expect, it, vi } from "vitest";

import { StubAdapter } from "./adapter/stub.ts";
import { MiresViewer } from "./mires-viewer.ts";
import { GIB, MIB } from "./size-guard.ts";

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

async function mount({ metadata = ct(8), max3d = 2048, maxTexture = 16384, canAnnotate = true } = {}) {
  vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(metadata))));
  const adapter = new StubAdapter();
  adapter.gpu = { max3dTextureSize: max3d, maxTextureSize: maxTexture };
  const el = document.createElement("mires-viewer") as MiresViewer;
  el.adapterFactory = async () => adapter;
  el.setAttribute("study-uid", "2.25.100");
  el.setAttribute("series-uid", "2.25.200");
  el.canAnnotate = canAnnotate;
  document.body.append(el);
  await vi.waitFor(() => expect(el.getAttribute("state")).toMatch(/ready|error/));
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

afterEach(() => {
  document.body.innerHTML = "";
  vi.unstubAllGlobals();
});

describe("a series within limits", () => {
  it("has no banner, and reserves the volume plus a labelmap for an annotate role when opened in 3D", async () => {
    const { el } = await mount();
    expect($(el, ".size-banner")).toBeNull();

    await click(el, '[data-layout="axial"]');

    // 64 × 64 × 8 × 2 B volume + 64 × 64 × 8 × 1 B labelmap reserve.
    expect(el.budget.used()).toBe(64 * 64 * 8 * 3);
  });

  it("reserves no labelmap for a view-only role", async () => {
    const { el } = await mount({ canAnnotate: false });

    await click(el, '[data-layout="axial"]');

    expect(el.budget.used()).toBe(64 * 64 * 8 * 2);
  });
});

describe("a series beyond the 3D texture limit", () => {
  it("opens as the full-resolution stack with a banner, and offers only reduced 3D", async () => {
    const { el, adapter } = await mount({ max3d: 32 });

    expect(el.getAttribute("state")).toBe("ready");
    expect(adapter.opened).toHaveLength(1);
    const banner = $(el, ".size-banner")!.textContent!;
    expect(banner).toContain("64 × 64 px exceed the GPU's 3D texture limit (32)");
    expect(banner).toContain("MPR, crosshairs and fusion are off");
    expect($$(el, "[data-layout]").map((b) => b.dataset.layout)).toEqual(["stack", "reduced"]);
    expect($(el, '[data-layout="reduced"]')!.textContent).toContain("Open reduced 3D (view only)");
    // Editing still works on the stack.
    expect(railTools(el)).toContain("Length");
    expect(railTools(el)).toContain("ArrowAnnotate");
  });

  it("reduced 3D opens a decimated volume in three views with navigation and crosshairs only", async () => {
    const { el, adapter } = await mount({ max3d: 32 });

    await click(el, '[data-layout="reduced"]');

    expect(adapter.volumes).toHaveLength(1);
    expect(adapter.volumes[0].options?.decimation).toEqual([2, 2, 1]);
    expect(adapter.volumes[0].orientations).toHaveLength(3);
    expect(railTools(el)).toEqual(["WindowLevel", "Pan", "Zoom", "StackScroll", "Crosshairs"]);
    expect($(el, ".size-banner")!.textContent).toContain("Reduced 3D (view only)");
    // No labelmap reserve on a reduced grid: 32 × 32 × 8 × 2 B.
    expect(el.budget.used()).toBe(32 * 32 * 8 * 2);

    // Orientation buttons stay reduced; Stack goes back to full resolution.
    await click(el, '[data-layout="coronal"]');
    expect(adapter.volumes).toHaveLength(1);
    await click(el, '[data-layout="stack"]');
    expect(railTools(el)).toContain("Length");
  });

  it("refuses the full volume through keys too (V does nothing on the stack)", async () => {
    const { el, adapter } = await mount({ max3d: 32 });
    el.dispatchEvent(new KeyboardEvent("keydown", { key: "v", bubbles: true, composed: true }));
    await el.updateComplete;
    expect(adapter.volumes).toHaveLength(0);
  });
});

describe("refusals", () => {
  it("refuses a 2D image wider than MAX_TEXTURE_SIZE", async () => {
    const { el, adapter } = await mount({ metadata: ct(1, 4096), maxTexture: 2048 });

    expect(el.getAttribute("state")).toBe("error");
    expect($(el, "[role=alert]")!.textContent).toContain("texture limit (2048 px)");
    expect(adapter.opened).toHaveLength(0);
  });

  it("refuses a volume over budget when added, and leaves the stack open", async () => {
    const { el, adapter } = await mount();
    el.budget.reserve([{ id: "volume:other", series: "other", kind: "volume", bytes: 2.5 * GIB - MIB / 16 }]);

    await click(el, '[data-layout="axial"]');

    expect(adapter.volumes).toHaveLength(0);
    expect(adapter.closed).toHaveLength(0);
    expect($(el, ".refusal")!.textContent).toContain("Too large for 3D");
    expect(el.stackState).toBeDefined();
  });

  it("shows a 'too large' message for CS3D cache errors and goes back to the stack", async () => {
    const { el, adapter } = await mount();
    adapter.volumeFailWith = new Error("CACHE_SIZE_EXCEEDED");

    await click(el, '[data-layout="axial"]');

    await vi.waitFor(() => expect(el.stackState).toBeDefined());
    expect(el.getAttribute("state")).toBe("ready");
    expect($(el, ".refusal")!.textContent).toContain("Too large to open");
    expect(el.budget.used()).toBe(0);
  });

  it("goes back to the stack when the cache refuses slices while the volume streams", async () => {
    const { el, adapter } = await mount();
    await click(el, '[data-layout="three"]');

    adapter.volumes[0].tooLarge();

    await vi.waitFor(() => expect(el.stackState).toBeDefined());
    expect(adapter.closed).toContain(adapter.volumes[0]);
    expect($(el, ".refusal")!.textContent).toContain("Too large to open");
    expect(el.budget.used()).toBe(0);
  });

  it("panels can refuse with a message through the context, dismissible", async () => {
    const { el } = await mount();

    el.refuse("Can't fuse: too big.");
    await el.updateComplete;
    expect($(el, ".refusal")!.textContent).toContain("Can't fuse");

    $(el, ".refusal button")!.click();
    await el.updateComplete;
    expect($(el, ".refusal")).toBeNull();
  });
});
