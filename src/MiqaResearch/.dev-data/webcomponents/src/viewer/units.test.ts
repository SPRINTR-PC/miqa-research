import { describe, expect, it } from "vitest";

import { unitTooltip } from "./units.ts";

describe("unitTooltip: plain language for CS3D's raw unit suffixes", () => {
  it.each([
    ["mm", /pixel spacing/i],
    ["mm Proj", /detector plane.*overestimated/i],
    ["mm ERMF", /estimated radiographic magnification/i],
    ["mm Unknown", /unverified/i],
    ["mm User", /calibrated by a user/i],
    ["cm US Region", /ultrasound region/i],
    ["px", /no pixel spacing/i],
  ])("explains %s", (unit, expected) => {
    expect(unitTooltip(unit)).toMatch(expected);
  });

  it("explains area units like their length unit", () => {
    expect(unitTooltip("mm² Proj")).toBe(unitTooltip("mm Proj"));
    expect(unitTooltip("px²")).toBe(unitTooltip("px"));
  });

  it("has no tooltip for a unit it doesn't know", () => {
    expect(unitTooltip("furlong")).toBe("");
  });
});
