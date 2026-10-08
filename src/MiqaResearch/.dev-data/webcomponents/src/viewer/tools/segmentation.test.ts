// #286 segment tools in the registry: rail, keys, role gating, and their right-drag erase twins.
import { describe, expect, it } from "vitest";

import { workstationBindings } from "./bindings.ts";
import { tools } from "./index.ts";
import { eraseTwin, SEGMENT_TOOLS, segmentBindings } from "./segmentation.ts";

const segmentRail = (viewport: "stack" | "volume" | "wsi", canAnnotate: boolean) =>
  tools
    .rail({ viewport, canAnnotate })
    .find((g) => g.group === "segment")
    ?.tools.map((t) => `${t.id}:${t.key}`);

describe("segment tools", () => {
  it("are on the rail for annotate roles on stacks and volumes, with keys g d k q j y m", () => {
    const expected = [
      "Brush:g",
      "Eraser:d",
      "PolygonSeg:k",
      "RectangleScissor:q",
      "CircleScissor:j",
      "SphereScissor:y",
      "RectangleROIThreshold:m",
    ];

    expect(segmentRail("stack", true)).toEqual(expected);
    expect(segmentRail("volume", true)).toEqual(expected);
  });

  it("are hidden from view-only roles, on WSI and in reduced 3D", () => {
    expect(segmentRail("stack", false)).toBeUndefined();
    expect(segmentRail("wsi", true)).toBeUndefined();
    expect(tools.available({ viewport: "volume", canAnnotate: true, viewOnly: true }).some((t) => t.group === "segment")).toBe(false);
  });

  it("erase with the same shape on right-drag; Eraser and threshold keep right-drag W/L", () => {
    expect(eraseTwin("Brush")).toBe("Eraser");
    expect(eraseTwin("PolygonSeg")).toBe("PolygonSegErase");
    expect(eraseTwin("RectangleScissor")).toBe("RectangleScissorErase");
    expect(eraseTwin("CircleScissor")).toBe("CircleScissorErase");
    expect(eraseTwin("SphereScissor")).toBe("SphereScissorErase");
    expect(eraseTwin("Eraser")).toBeUndefined();
    expect(eraseTwin("RectangleROIThreshold")).toBeUndefined();
    expect(eraseTwin("Length")).toBeUndefined();
  });

  it("segmentBindings puts the erase twin on the right button", () => {
    expect(segmentBindings({ primary: "Brush", viewport: "stack" })).toEqual(
      workstationBindings({ primary: "Brush", viewport: "stack", secondary: "Eraser" }),
    );
    expect(segmentBindings({ primary: "Length", viewport: "volume" }).WindowLevel).toEqual(["secondary"]);
  });

  it("segmentBindings: erase twin wins over a requested secondary (#284 overlay W/L), which applies otherwise", () => {
    const req = { viewport: "volume", secondary: "LayerWindowLevel" } as const;
    expect(segmentBindings({ ...req, primary: "Brush" }).Eraser).toEqual(["secondary"]);
    expect(segmentBindings({ ...req, primary: "Brush" }).LayerWindowLevel).toBeUndefined();
    expect(segmentBindings({ ...req, primary: "Length" }).LayerWindowLevel).toEqual(["secondary"]);
    expect(segmentBindings({ ...req, primary: "Length" }).WindowLevel).toBeUndefined();
    expect(segmentBindings({ primary: "Length", viewport: "volume" }).WindowLevel).toEqual(["secondary"]);
  });

  it("lists every segment tool id", () => {
    expect(SEGMENT_TOOLS).toHaveLength(7);
  });
});
