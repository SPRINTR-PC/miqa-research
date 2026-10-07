import { describe, expect, it } from "vitest";

import { workstationBindings } from "./bindings.ts";

describe("workstationBindings (spec: workstation mouse)", () => {
  it("binds left to the selected tool, right-drag W/L, middle pan, wheel scroll, Ctrl+wheel zoom on a stack", () => {
    expect(workstationBindings({ primary: "Length", viewport: "stack" })).toEqual({
      Length: ["primary"],
      WindowLevel: ["secondary"],
      Pan: ["middle"],
      StackScroll: ["wheel"],
      Zoom: ["ctrl+wheel"],
    });
  });

  it("gives a tool both buttons when it is selected and also has a fixed button", () => {
    expect(workstationBindings({ primary: "Pan", viewport: "stack" }).Pan).toEqual(["primary", "middle"]);
  });

  it("zooms with the plain wheel on a slide", () => {
    const wsi = workstationBindings({ primary: "Pan", viewport: "wsi" });

    expect(wsi.Zoom).toContain("wheel");
    expect(wsi.StackScroll).toBeUndefined();
    expect(wsi.WindowLevel).toBeUndefined();
  });

  it("lets the selected tool take over the right button (segment tools erase)", () => {
    const b = workstationBindings({ primary: "Brush", viewport: "stack", secondary: "Eraser" });

    expect(b.Eraser).toEqual(["secondary"]);
    expect(b.WindowLevel).toBeUndefined();
  });
});
