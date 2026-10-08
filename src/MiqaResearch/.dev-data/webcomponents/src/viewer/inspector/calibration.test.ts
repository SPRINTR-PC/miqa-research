// #281 in the chrome: calibration legend panel, burned-in badge, Calibrate tool + known-length form.
// Seam: <mires-viewer> with the stub adapter; what the element shows and asks of the view.
import { afterEach, describe, expect, it, vi } from "vitest";

import { StubAdapter, type StubStackView } from "../adapter/stub.ts";
import { MiresViewer } from "../mires-viewer.ts";

const CT = "1.2.840.10008.5.1.4.1.1.2";
const CR = "1.2.840.10008.5.1.4.1.1.1";
const SC = "1.2.840.10008.5.1.4.1.1.7";

function series(sopClass: string, modality: string, extra: Record<string, unknown> = {}) {
  return [1, 2].map((n) => ({
    "00080016": { vr: "UI", Value: [sopClass] },
    "00080018": { vr: "UI", Value: [`2.25.${n}`] },
    "00080060": { vr: "CS", Value: [modality] },
    "00200013": { vr: "IS", Value: [n] },
    ...extra,
  }));
}

async function mount(metadata: unknown, { canAnnotate = false } = {}): Promise<{ el: MiresViewer; view: StubStackView }> {
  vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(metadata))));
  const adapter = new StubAdapter();
  const el = document.createElement("mires-viewer") as MiresViewer;
  el.adapterFactory = async () => adapter;
  el.setAttribute("study-uid", "2.25.100");
  el.setAttribute("series-uid", "2.25.200");
  if (canAnnotate) el.setAttribute("can-annotate", "");
  document.body.append(el);
  await vi.waitFor(() => expect(el.getAttribute("state")).toBe("ready"));
  await el.updateComplete;
  return { el, view: adapter.views[0] };
}

const $ = (el: MiresViewer, selector: string) => el.shadowRoot!.querySelector<HTMLElement>(selector);
const railTools = (el: MiresViewer) => [...el.shadowRoot!.querySelectorAll<HTMLElement>(".rail [data-tool]")].map((b) => b.dataset.tool);

async function emit(el: MiresViewer, view: StubStackView, change: Parameters<StubStackView["emit"]>[0]) {
  view.emit(change);
  await el.updateComplete;
}

afterEach(() => {
  document.body.innerHTML = "";
  vi.unstubAllGlobals();
});

describe("calibration legend", () => {
  it("explains detector-plane spacing on a CR", async () => {
    const { el, view } = await mount(series(CR, "CR"));

    await emit(el, view, { unit: "mm Proj" });

    expect($(el, ".calibration .badge")?.textContent).toBe("Detector plane (Proj)");
    expect($(el, ".calibration")?.textContent).toMatch(/overestimated/);
  });

  it("labels an SC's spacing as unverified", async () => {
    const { el, view } = await mount(series(SC, "OT", { "00280030": { vr: "DS", Value: [0.5, 0.5] } }));

    await emit(el, view, { unit: "mm Unknown" });

    expect($(el, ".calibration .badge")?.textContent).toBe("Unverified (SC)");
    expect($(el, ".calibration")?.textContent).toContain("Spacing from secondary capture — unverified");
  });

  it("is not shown for CT", async () => {
    const { el, view } = await mount(series(CT, "CT"));

    await emit(el, view, { unit: "mm" });

    expect($(el, ".calibration")).toBeNull();
  });
});

describe("burned-in badge", () => {
  it("warns when the image says BurnedInAnnotation=YES", async () => {
    const { el } = await mount(series(CT, "CT", { "00280301": { vr: "CS", Value: ["YES"] } }));

    expect($(el, ".burned-in")?.textContent).toMatch(/burned-in/i);
  });

  it("warns for an SC without the tag", async () => {
    const { el } = await mount(series(SC, "OT"));

    expect($(el, ".burned-in")).not.toBeNull();
  });

  it("is not shown for a CT without the tag", async () => {
    const { el } = await mount(series(CT, "CT"));

    expect($(el, ".burned-in")).toBeNull();
  });
});

describe("Calibrate tool", () => {
  it("is on the stack rail and key C for annotate roles only", async () => {
    const annotator = await mount(series(CR, "CR"), { canAnnotate: true });
    expect(railTools(annotator.el)).toContain("Calibrate");

    document.body.innerHTML = "";
    const viewer = await mount(series(CR, "CR"));
    expect(railTools(viewer.el)).not.toContain("Calibrate");
    viewer.el.dispatchEvent(new KeyboardEvent("keydown", { key: "c", bubbles: true, composed: true }));
    expect(viewer.view.state().activeTool).not.toBe("Calibrate");
  });

  it("asks for the known length of the drawn line and applies it to the view", async () => {
    const { el, view } = await mount(series(CR, "CR"), { canAnnotate: true });
    await emit(el, view, { unit: "mm Proj", pendingCalibration: { length: 42.5, unit: "mm Proj" } });

    expect($(el, ".calibration form")?.textContent).toContain("42.5 mm Proj");
    const input = $(el, ".calibration input") as HTMLInputElement;
    input.value = "50";
    $(el, ".calibration form")!.dispatchEvent(new Event("submit", { cancelable: true }));
    await el.updateComplete;

    expect(view.calibrations).toEqual([50]);
    expect($(el, ".calibration .badge")?.textContent).toBe("User-calibrated");
    expect($(el, ".calibration form")).toBeNull();
  });

  it("can be cancelled, leaving the spacing alone", async () => {
    const { el, view } = await mount(series(CT, "CT"), { canAnnotate: true });
    await emit(el, view, { pendingCalibration: { length: 10, unit: "mm" } });

    ($(el, ".calibration button[data-action=cancel]") as HTMLButtonElement).click();
    await el.updateComplete;

    expect(view.calibrations).toEqual([]);
    expect($(el, ".calibration")).toBeNull();
  });
});
