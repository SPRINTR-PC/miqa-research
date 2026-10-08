import { afterEach, describe, expect, it } from "vitest";

import { DEFAULT_SPLIT, SPLIT_STORAGE_KEY, clampSplit, cycleOrientation, loadSplit, saveSplit, swapIntoMain, threeViews } from "./layout.ts";

afterEach(() => localStorage.clear());

describe("volume layout", () => {
  it("V cycles axial → sagittal → coronal → axial", () => {
    expect(cycleOrientation("axial")).toBe("sagittal");
    expect(cycleOrientation("sagittal")).toBe("coronal");
    expect(cycleOrientation("coronal")).toBe("axial");
  });

  it("three views put the chosen orientation in the big view, the others stacked on the right", () => {
    expect(threeViews("axial")).toEqual(["axial", "sagittal", "coronal"]);
    expect(threeViews("coronal")).toEqual(["coronal", "axial", "sagittal"]);
  });

  it("double-click swaps a small view into the big one", () => {
    expect(swapIntoMain(["axial", "sagittal", "coronal"], 2)).toEqual(["coronal", "sagittal", "axial"]);
    expect(swapIntoMain(["axial", "sagittal", "coronal"], 0)).toEqual(["axial", "sagittal", "coronal"]);
  });

  it("the split stays within 25–85%", () => {
    expect(clampSplit(10)).toBe(25);
    expect(clampSplit(90)).toBe(85);
    expect(clampSplit(50.4)).toBe(50);
  });

  it("the split is remembered per browser, default 66%", () => {
    expect(loadSplit()).toBe(DEFAULT_SPLIT);
    saveSplit(40);
    expect(localStorage.getItem(SPLIT_STORAGE_KEY)).toBe("40");
    expect(loadSplit()).toBe(40);
    localStorage.setItem(SPLIT_STORAGE_KEY, "nonsense");
    expect(loadSplit()).toBe(66);
    localStorage.setItem(SPLIT_STORAGE_KEY, "99");
    expect(loadSplit()).toBe(85);
  });
});
