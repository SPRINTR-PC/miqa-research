// #280 chrome B on a stack: series list, tool rail, inspector, keys, role gating.
// Seam: <mires-viewer> with the stub adapter; what the element shows and asks of the view.
import { html } from "lit";
import { afterEach, describe, expect, it, vi } from "vitest";

import { StubAdapter, type StubStackView } from "./adapter/stub.ts";
import { inspector } from "./inspector/index.ts";
import { MiresViewer } from "./mires-viewer.ts";
import { seriesEntries } from "./test-fixtures.ts";

const CT_METADATA = [1, 2, 3].map((n) => ({
  "00080018": { vr: "UI", Value: [`2.25.${n}`] },
  "00080060": { vr: "CS", Value: ["CT"] },
  "0008103E": { vr: "LO", Value: ["Chest CT"] },
  "00200013": { vr: "IS", Value: [n] },
}));

async function mount({ canAnnotate = false } = {}): Promise<{ el: MiresViewer; view: StubStackView }> {
  vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(CT_METADATA))));
  const adapter = new StubAdapter();
  const el = document.createElement("mires-viewer") as MiresViewer;
  el.adapterFactory = async () => adapter;
  el.entries = seriesEntries(["2.25.200"], [], "2.25.100", {
    "2.25.200": { modality: "CT", description: "Chest CT", instances: 3 },
  });
  if (canAnnotate) el.setAttribute("can-annotate", "");
  document.body.append(el);
  await vi.waitFor(() => expect(el.getAttribute("state")).toBe("ready"));
  await el.updateComplete;
  return { el, view: adapter.views[0] };
}

const $ = (el: MiresViewer, selector: string) => el.shadowRoot!.querySelector<HTMLElement>(selector);
const $$ = (el: MiresViewer, selector: string) => [...el.shadowRoot!.querySelectorAll<HTMLElement>(selector)];
const railTools = (el: MiresViewer) => $$(el, ".rail [data-tool]").map((b) => b.dataset.tool);

async function press(el: MiresViewer, key: string, init: KeyboardEventInit = {}) {
  el.dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true, composed: true, ...init }));
  await el.updateComplete;
}

afterEach(() => {
  document.body.innerHTML = "";
  vi.unstubAllGlobals();
});

describe("tool rail", () => {
  it("groups the stack tools under Nav, Measure, Annot. and Segment for an annotate role", async () => {
    const { el } = await mount({ canAnnotate: true });

    expect($$(el, ".rail h6").map((h) => h.textContent)).toEqual(["Nav", "Measure", "Annot.", "Segment"]);
    expect(railTools(el)).toEqual([
      "WindowLevel", "Pan", "Zoom", "StackScroll",
      "Length", "Angle", "Bidirectional", "Probe", "RectangleROI", "EllipticalROI", "PlanarFreehandROI", "Calibrate",
      "ArrowAnnotate",
      "Brush", "Eraser", "PolygonSeg", "RectangleScissor", "CircleScissor", "SphereScissor", "RectangleROIThreshold",
    ]);
  });

  it("gives a view-only user no annotate tools", async () => {
    const { el } = await mount();

    expect(railTools(el)).not.toContain("ArrowAnnotate");
    expect($$(el, ".rail h6").map((h) => h.textContent)).toEqual(["Nav", "Measure"]);
  });

  it("starts with Window/Level on the left button", async () => {
    const { el, view } = await mount();

    expect(view.current.activeTool).toBe("WindowLevel");
    expect($(el, '[data-tool="WindowLevel"]')!.getAttribute("aria-pressed")).toBe("true");
  });

  it("selects a tool when its button is clicked", async () => {
    const { el, view } = await mount();

    $(el, '[data-tool="Angle"]')!.click();
    await el.updateComplete;

    expect(view.current.activeTool).toBe("Angle");
    expect($(el, '[data-tool="Angle"]')!.getAttribute("aria-pressed")).toBe("true");
    expect($(el, '[data-tool="WindowLevel"]')!.getAttribute("aria-pressed")).toBe("false");
  });

  it("shows each tool's shortcut key in its tooltip", async () => {
    const { el } = await mount();

    expect($(el, '[data-tool="Length"]')!.title).toBe("Length (L)");
  });
});

describe("keys", () => {
  it("selects a tool by its single-key shortcut", async () => {
    const { el, view } = await mount();

    await press(el, "l");

    expect(view.current.activeTool).toBe("Length");
  });

  it("ignores annotate-tool keys for a view-only user", async () => {
    const { el, view } = await mount();

    await press(el, "t");

    expect(view.current.activeTool).toBe("WindowLevel");
  });

  it("selects annotate tools by key for an annotate role", async () => {
    const { el, view } = await mount({ canAnnotate: true });

    await press(el, "t");

    expect(view.current.activeTool).toBe("ArrowAnnotate");
  });

  it("applies window presets with digits: 2 = Lung, 0 = DICOM default", async () => {
    const { el, view } = await mount();
    view.defaultVoi = { lower: -160, upper: 239 };

    await press(el, "2");
    expect(view.current.voi).toEqual({ lower: -1350, upper: 149 });

    await press(el, "0");
    expect(view.current.voi).toEqual({ lower: -160, upper: 239 });
  });

  it("inverts with I and resets the view with Esc", async () => {
    const { el, view } = await mount();

    await press(el, "i");
    expect(view.current.invert).toBe(true);

    await press(el, "Escape");
    expect(view.current.invert).toBe(false);
    expect(view.resets).toBe(1);
  });

  it("leaves modified keys to the browser (Ctrl+L is not Length)", async () => {
    const { el, view } = await mount();

    await press(el, "l", { ctrlKey: true });

    expect(view.current.activeTool).toBe("WindowLevel");
  });
});

describe("series list", () => {
  it("lists the open series with modality, description and image count", async () => {
    const { el } = await mount();

    const row = $(el, ".series [data-series-uid='2.25.200']")!;
    expect(row.textContent).toContain("CT");
    expect(row.textContent).toContain("Chest CT");
    expect(row.textContent).toContain("3 images");
  });
});

describe("inspector", () => {
  it("offers the CT window presets with their keys", async () => {
    const { el, view } = await mount();

    const lung = $$(el, ".inspector [data-preset]").find((b) => b.textContent!.includes("Lung"))!;
    expect(lung.textContent).toContain("2");
    lung.click();

    expect(view.current.voi).toEqual({ lower: -1350, upper: 149 });
  });

  it("explains the workstation mouse", async () => {
    const { el } = await mount();

    expect($(el, ".inspector")!.textContent).toContain("Right drag: window/level");
  });

  it("renders panels registered by other modules, in order", async () => {
    inspector.register({ id: "test-first", order: 1, render: (ctx) => html`<section class="panel" id="test-first">tool ${ctx.activeTool}</section>` });
    try {
      const { el } = await mount();

      const first = $(el, ".inspector > section")!;
      expect(first.id).toBe("test-first");
      expect(first.textContent).toContain("tool WindowLevel");
    } finally {
      inspector.unregister("test-first");
    }
  });
});

describe("measurement unit", () => {
  it("shows CS3D's raw unit with a plain-language tooltip", async () => {
    const { el, view } = await mount();

    view.emit({ unit: "mm Proj" });
    await el.updateComplete;

    const unit = $(el, ".unit")!;
    expect(unit.textContent!.trim()).toBe("mm Proj");
    expect(unit.title).toMatch(/detector plane/i);
  });
});
