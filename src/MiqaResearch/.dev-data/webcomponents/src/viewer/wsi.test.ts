import { describe, expect, it } from "vitest";

import type { DicomJsonInstance, LoadedSeries } from "./series.ts";
import { geometricTextLines, isWholeSlide, tilesCacheSize, wsiImageIds } from "./wsi.ts";

const WSI_SOP_CLASS = "1.2.840.10008.5.1.4.1.1.77.1.6";
const CT_SOP_CLASS = "1.2.840.10008.5.1.4.1.1.2";

function instance(sop: string, tags: Record<string, unknown> = {}): DicomJsonInstance {
  const json: DicomJsonInstance = {
    "00080016": { vr: "UI", Value: [WSI_SOP_CLASS] },
    "00080018": { vr: "UI", Value: [sop] },
  };
  for (const [tag, value] of Object.entries(tags)) json[tag] = { vr: "US", Value: [value] };
  return json;
}

const ROWS = "00280010";
const COLUMNS = "00280011";

function series(...instances: { json: DicomJsonInstance; frames: number }[]): LoadedSeries {
  const root = "wadors:/w/studies/1/series/2";
  return {
    ref: { wadoRoot: "/w", studyUid: "1", seriesUid: "2" },
    images: instances.flatMap(({ json, frames }) =>
      Array.from({ length: frames }, (_, f) => ({
        imageId: `${root}/instances/${json["00080018"].Value![0]}/frames/${f + 1}`,
        instance: json,
      })),
    ),
  };
}

describe("tilesCacheSize", () => {
  it("fits 512 MiB of RGBA tiles: 512 tiles of 512²", () => {
    expect(tilesCacheSize([instance("a", { [ROWS]: 512, [COLUMNS]: 512 })])).toBe(512);
  });

  it("scales with the tile size: 2048 tiles of 256², 128 tiles of 1024²", () => {
    expect(tilesCacheSize([instance("a", { [ROWS]: 256, [COLUMNS]: 256 })])).toBe(2048);
    expect(tilesCacheSize([instance("a", { [ROWS]: 1024, [COLUMNS]: 1024 })])).toBe(128);
  });

  it("budgets for the largest tile of the pyramid and rounds down", () => {
    const levels = [
      instance("a", { [ROWS]: 240, [COLUMNS]: 240 }),
      instance("b", { [ROWS]: 500, [COLUMNS]: 300 }),
    ];
    // 536870912 / (500 × 300 × 4) = 894.78…
    expect(tilesCacheSize(levels)).toBe(894);
  });

  it("falls back to 512² tiles when the metadata has no tile size", () => {
    expect(tilesCacheSize([instance("a")])).toBe(512);
  });
});

describe("isWholeSlide", () => {
  it("is true for a VL Whole Slide Microscopy series, false otherwise", () => {
    expect(isWholeSlide(series({ json: instance("a"), frames: 4 }))).toBe(true);
    const ct = instance("c");
    ct["00080016"] = { vr: "UI", Value: [CT_SOP_CLASS] };
    expect(isWholeSlide(series({ json: ct, frames: 1 }))).toBe(false);
  });
});

describe("wsiImageIds", () => {
  it("gives one imageId per instance (pyramid level), not per tile", () => {
    const loaded = series({ json: instance("a"), frames: 4 }, { json: instance("b"), frames: 1 });

    expect(wsiImageIds(loaded).map((i) => i.imageId)).toEqual([
      "wadors:/w/studies/1/series/2/instances/a/frames/1",
      "wadors:/w/studies/1/series/2/instances/b/frames/1",
    ]);
  });
});

describe("geometricTextLines", () => {
  const round = (n: number) => n.toFixed(2);

  it("keeps length, area and perimeter, and drops intensity statistics", () => {
    const stats = {
      area: 0.5,
      areaUnit: "mm²",
      mean: Number.NaN,
      stdDev: Number.NaN,
      max: Number.NaN,
      min: 3,
      modalityUnit: "",
      perimeter: 2.75,
      unit: "mm",
    };

    expect(geometricTextLines(stats, round)).toEqual(["Area: 0.50 mm²", "Perimeter: 2.75 mm"]);
  });

  it("shows a length", () => {
    expect(geometricTextLines({ length: 1.234, unit: "mm" }, round)).toEqual(["1.23 mm"]);
  });

  it("shows nothing for missing stats", () => {
    expect(geometricTextLines(undefined, round)).toEqual([]);
  });
});
