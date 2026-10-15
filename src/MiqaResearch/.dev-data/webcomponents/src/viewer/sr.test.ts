import { describe, expect, it } from "vitest";

import {
  CALIBRATION_QUALIFIER,
  annotateReport,
  calibrationType,
  droppedTools,
  readUserCalibrations,
  ucumUnit,
  type SrItem,
} from "./sr.ts";

/** A NUM content item as dcmjs' TID 300 builders make it (single items, not arrays). */
const num = (code: string, meaning: string, value: number, unit: string, scoord = false): SrItem => ({
  RelationshipType: "CONTAINS",
  ValueType: "NUM",
  ConceptNameCodeSequence: { CodeValue: code, CodingSchemeDesignator: "SCT", CodeMeaning: meaning },
  MeasuredValueSequence: {
    MeasurementUnitsCodeSequence: { CodeValue: unit, CodingSchemeDesignator: "UCUM", CodeMeaning: unit },
    NumericValue: value,
  },
  ...(scoord ? { ContentSequence: [{ RelationshipType: "INFERRED FROM", ValueType: "SCOORD", GraphicType: "POLYLINE" }] } : {}),
});

const group = (...items: SrItem[]): SrItem => ({
  RelationshipType: "CONTAINS",
  ValueType: "CONTAINER",
  ConceptNameCodeSequence: { CodeValue: "125007", CodingSchemeDesignator: "DCM", CodeMeaning: "Measurement Group" },
  ContentSequence: [
    { ValueType: "TEXT", ConceptNameCodeSequence: { CodeValue: "112039", CodingSchemeDesignator: "DCM", CodeMeaning: "Tracking Identifier" }, TextValue: "x" },
    ...items,
  ],
});

/** A TID 1500 report as dcmjs' MeasurementReport.generateReport leaves it: groups under "Imaging Measurements". */
const report = (...groups: SrItem[]): SrItem => ({
  Modality: "SR",
  ContentSequence: [
    { ValueType: "CODE", ConceptNameCodeSequence: { CodeValue: "121049", CodingSchemeDesignator: "DCM", CodeMeaning: "Language of Content Item and Descendants" } },
    {
      ValueType: "CONTAINER",
      ConceptNameCodeSequence: { CodeValue: "126010", CodingSchemeDesignator: "DCM", CodeMeaning: "Imaging Measurements" },
      ContentSequence: groups,
    },
  ],
});

const groupsOf = (dataset: SrItem) => (dataset.ContentSequence as SrItem[])[1].ContentSequence as SrItem[];
const unitOf = (item: SrItem) => code(code(item.MeasuredValueSequence).MeasurementUnitsCodeSequence);
const items = (g: SrItem) => g.ContentSequence as SrItem[];
/** First item of a sequence, whether an array or (dcmjs' builders) a single item. */
const code = (seq: unknown) => (Array.isArray(seq) ? seq[0] : seq) as SrItem;
const qualifier = (g: SrItem) => items(g).find((i) => code(i.ConceptNameCodeSequence)?.CodeValue === CALIBRATION_QUALIFIER.CodeValue);

describe("ucumUnit", () => {
  it("maps CS3D's raw units to true UCUM units, uncalibrated as {pixels}", () => {
    expect(ucumUnit("mm")?.CodeValue).toBe("mm");
    expect(ucumUnit("mm Proj")?.CodeValue).toBe("mm");
    expect(ucumUnit("mm User")?.CodeValue).toBe("mm");
    expect(ucumUnit("mm² ERMF")?.CodeValue).toBe("mm2");
    expect(ucumUnit("cm US Region")?.CodeValue).toBe("cm");
    expect(ucumUnit("px")?.CodeValue).toBe("{pixels}");
    expect(ucumUnit("px²")?.CodeValue).toBe("{square pixels}");
    expect(ucumUnit("px")?.CodingSchemeDesignator).toBe("UCUM");
    expect(ucumUnit("HU")).toBeUndefined();
  });
});

describe("calibrationType", () => {
  it("is the suffix CS3D adds, Uncalibrated for px, none for plain mm", () => {
    expect(calibrationType("mm Proj")).toBe("Proj");
    expect(calibrationType("mm² User")).toBe("User");
    expect(calibrationType("cm US Region")).toBe("US Region");
    expect(calibrationType("px")).toBe("Uncalibrated");
    expect(calibrationType("mm")).toBe("");
  });
});

describe("annotateReport", () => {
  it("stores lengths and areas in their true UCUM unit, never px values labelled mm", () => {
    // dcmjs labels every Length "mm" and px² areas "1", whatever CS3D measured in.
    const dataset = report(
      group(num("410668003", "Length", 120, "mm", true)),
      group(num("131191004", "Perimeter", 40, "mm", true), num("42798000", "Area", 100, "1"), num("373098007", "Mean", 5, "[hnsf'U]")),
    );

    annotateReport(dataset, [{ unit: "px" }, { unit: "px", areaUnit: "px²" }]);

    const [length, roi] = groupsOf(dataset);
    expect(unitOf(items(length)[1]).CodeValue).toBe("{pixels}");
    expect(unitOf(items(roi)[1]).CodeValue).toBe("{pixels}");
    expect(unitOf(items(roi)[2]).CodeValue).toBe("{square pixels}");
    expect(unitOf(items(roi)[3]).CodeValue).toBe("[hnsf'U]"); // not spatial: untouched
  });

  it("adds the calibration type as a qualifier in the measurement group", () => {
    const dataset = report(group(num("410668003", "Length", 12, "mm", true)), group(num("410668003", "Length", 30, "mm", true)));

    annotateReport(dataset, [{ unit: "mm Proj" }, { unit: "mm" }]);

    const [proj, plain] = groupsOf(dataset);
    const q = qualifier(proj)!;
    expect(q.RelationshipType).toBe("HAS CONCEPT MOD");
    expect(q.ValueType).toBe("CODE");
    expect(code(q.ConceptCodeSequence).CodeValue).toBe("Proj");
    expect(unitOf(items(proj)[1]).CodeValue).toBe("mm");
    expect(qualifier(plain)).toBeUndefined(); // tomographic mm: no calibration to qualify
  });

  it("stores a User calibration's reference line and known length, which read back", () => {
    const user = {
      sopClassUid: "1.2.840.10008.5.1.4.1.1.7",
      sopInstanceUid: "2.25.77",
      line: [[10, 20], [130, 20]] as [[number, number], [number, number]],
      knownLengthMm: 50,
    };
    const dataset = report(group(num("410668003", "Length", 49.6, "mm", true)));

    annotateReport(dataset, [{ unit: "mm User", user }]);

    const g = groupsOf(dataset)[0];
    expect(code(qualifier(g)!.ConceptCodeSequence).CodeValue).toBe("User");
    const container = items(g).find((i) => i.ValueType === "CONTAINER")!;
    const known = items(container)[0];
    expect(known.ValueType).toBe("NUM");
    expect(unitOf(known).CodeValue).toBe("mm");
    expect(Number(code(known.MeasuredValueSequence).NumericValue)).toBe(50);
    const line = items(known)[0];
    expect(line.ValueType).toBe("SCOORD");
    expect(line.GraphicType).toBe("POLYLINE");
    expect(line.GraphicData).toEqual([10, 20, 130, 20]);
    const image = items(line)[0];
    expect(code(image.ReferencedSOPSequence).ReferencedSOPInstanceUID).toBe("2.25.77");
    // The adapter reads a group's first NUM as its measurement: the calibration stays nested.
    expect(items(g).filter((i) => i.ValueType === "NUM")).toHaveLength(1);

    expect(readUserCalibrations(dataset)).toEqual([user]);
  });

  it("reads one calibration per image even when several groups carry it", () => {
    const user = { sopClassUid: "1.2.3", sopInstanceUid: "2.25.1", frame: 2, line: [[0, 0], [3, 4]] as [[number, number], [number, number]], knownLengthMm: 10 };
    const dataset = report(group(num("410668003", "Length", 1, "mm", true)), group(num("410668003", "Length", 2, "mm", true)));
    annotateReport(dataset, [{ unit: "mm User", user }, { unit: "mm User", user }]);

    expect(readUserCalibrations(dataset)).toEqual([user]);
  });

  it("reads nothing from a report without calibrations", () => {
    expect(readUserCalibrations(report(group(num("410668003", "Length", 1, "mm", true))))).toEqual([]);
    expect(readUserCalibrations({ Modality: "SR" })).toEqual([]);
  });
});

describe("droppedTools", () => {
  it("lists tools the adapter can't export to SR, once each", () => {
    expect(droppedTools(["Length", "SplineROI", "PlanarFreehandROI", "SplineROI", "LivewireContour"])).toEqual([
      "LivewireContour",
      "SplineROI",
    ]);
    expect(droppedTools(["Length", "Angle", "ArrowAnnotate", "EllipticalROI", "RectangleROI", "Probe", "Bidirectional"])).toEqual([]);
  });
});
