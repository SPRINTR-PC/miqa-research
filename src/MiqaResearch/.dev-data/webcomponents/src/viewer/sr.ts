// SR TID 1500 (#289, spec "2D spacing and calibration" → SR persistence, #200). Pure: works on the
// naturalized dataset dcmjs builds (adapter/cornerstone/annotations.ts runs CS3D's adapters first).
//
// - Units: every length/area is stored in its true UCUM unit (`mm`, `cm`, or `{pixels}` /
//   `{square pixels}` when uncalibrated). dcmjs labels every Length `mm` and px areas `1`, so the
//   units CS3D measured in (`mm Proj`, `px`, …) are rewritten here.
// - Qualifier: the calibration type (CS3D's unit suffix; `Uncalibrated` for px) as a HAS CONCEPT MOD
//   CODE item in the measurement group. Plain `mm` (CT, MR, PET, WSI) has none.
// - User calibration: a nested container holding the known length (NUM, mm) inferred from the
//   reference line (SCOORD POLYLINE in image pixels) on its image, so it can be audited and reapplied
//   on reopen (`readUserCalibrations`). Nested, because the adapter takes a group's first NUM (or any
//   top-level SCOORD) as the measurement itself.

/** A naturalized DICOM item (dcmjs): sequences are arrays or, from dcmjs' TID 300 builders, single items. */
export type SrItem = Record<string, unknown>;

/** The tools `@cornerstonejs/adapters` exports to SR (toolType names); others are dropped on export. */
export const EXPORTABLE_TOOLS: readonly string[] = [
  "Length",
  "Angle",
  "CobbAngle",
  "Bidirectional",
  "Probe",
  "RectangleROI",
  "EllipticalROI",
  "CircleROI",
  "PlanarFreehandROI",
  "ArrowAnnotate",
  "UltrasoundDirectionalTool",
  "KeyImage",
];

/** Tools in `toolNames` that the SR can't hold (warned about before saving), once each, sorted. */
export function droppedTools(toolNames: string[]): string[] {
  return [...new Set(toolNames.filter((t) => !EXPORTABLE_TOOLS.includes(t)))].sort();
}

/** Spacing calibration of one image by the user (Calibrate tool, #281). */
export interface UserCalibration {
  sopClassUid: string;
  sopInstanceUid: string;
  /** 1-based frame of a multi-frame image. */
  frame?: number;
  /** Reference line end points in image pixel coordinates (column, row). */
  line: [[number, number], [number, number]];
  knownLengthMm: number;
}

/** What CS3D measured one annotation in: its raw units, and the User calibration of its image. */
export interface MeasurementUnits {
  /** Raw length unit (`mm`, `mm Proj`, `px`, `cm US Region`, …). */
  unit?: string;
  /** Raw area unit (`mm²`, `px²`, …). */
  areaUnit?: string;
  user?: UserCalibration;
}

const SCHEME = "99MIRES";
const UCUM = { CodingSchemeDesignator: "UCUM", CodingSchemeVersion: "1.4" };

export const CALIBRATION_QUALIFIER = { CodeValue: "SpacingCalib", CodingSchemeDesignator: SCHEME, CodeMeaning: "Spacing Calibration" };
const USER_CALIBRATION = { CodeValue: "UserCalibration", CodingSchemeDesignator: SCHEME, CodeMeaning: "User Spacing Calibration" };
const KNOWN_LENGTH = { CodeValue: "CalKnownLength", CodingSchemeDesignator: SCHEME, CodeMeaning: "Calibration Known Length" };

const UNITS: Record<string, { CodeValue: string; CodeMeaning: string }> = {
  mm: { CodeValue: "mm", CodeMeaning: "millimeter" },
  cm: { CodeValue: "cm", CodeMeaning: "centimeter" },
  "mm²": { CodeValue: "mm2", CodeMeaning: "square millimeter" },
  "cm²": { CodeValue: "cm2", CodeMeaning: "square centimeter" },
  px: { CodeValue: "{pixels}", CodeMeaning: "pixels" },
  "px²": { CodeValue: "{square pixels}", CodeMeaning: "square pixels" },
};

/** UCUM code for CS3D's raw unit (`mm Proj` → mm, `px` → {pixels}); undefined for non-spatial units. */
export function ucumUnit(rawUnit: string): SrItem | undefined {
  const unit = UNITS[rawUnit.trim().split(" ")[0]];
  return unit && { ...unit, ...UCUM };
}

/** Calibration type of CS3D's raw unit: its suffix (`Proj`, `User`, `US Region`), `Uncalibrated` for px, "" for plain mm. */
export function calibrationType(rawUnit: string): string {
  const [base, ...suffix] = rawUnit.trim().split(" ");
  if (base.startsWith("px")) return "Uncalibrated";
  return suffix.join(" ");
}

const toArray = (value: unknown): SrItem[] => (value === undefined || value === null ? [] : Array.isArray(value) ? value : [value]) as SrItem[];
const codeOf = (item: SrItem, key = "ConceptNameCodeSequence") => toArray(item[key])[0] as SrItem | undefined;
const isCode = (item: SrItem, code: { CodeValue: string; CodingSchemeDesignator: string }, key?: string) => {
  const c = codeOf(item, key);
  return c?.CodeValue === code.CodeValue && c?.CodingSchemeDesignator === code.CodingSchemeDesignator;
};

/** Measurement groups of a TID 1500 report, in order. */
function measurementGroups(dataset: SrItem): SrItem[] {
  const measurements = toArray(dataset.ContentSequence).find((i) => codeOf(i)?.CodeValue === "126010");
  return toArray(measurements?.ContentSequence).filter((i) => codeOf(i)?.CodeValue === "125007");
}

const AREA_CONCEPTS = new Set(["42798000"]);
const LENGTH_CONCEPTS = new Set(["410668003", "131191004", "103339001", "103340004", "131190003", "81827009"]);
const AREA_UNITS = new Set(["mm2", "cm2"]);
const LENGTH_UNITS = new Set(["mm", "cm"]);

/** Whether a NUM is a length or an area (by concept, else by dcmjs' unit); undefined for intensity stats, angles, … */
function dimension(item: SrItem): "length" | "area" | undefined {
  const concept = codeOf(item)?.CodeValue as string | undefined;
  const unit = codeOf(toArray(item.MeasuredValueSequence)[0] ?? {}, "MeasurementUnitsCodeSequence")?.CodeValue as string | undefined;
  if (AREA_CONCEPTS.has(concept ?? "") || AREA_UNITS.has(unit ?? "")) return "area";
  if (LENGTH_CONCEPTS.has(concept ?? "") || LENGTH_UNITS.has(unit ?? "")) return "length";
  return undefined;
}

function setUnit(item: SrItem, unit: SrItem): void {
  const measured = toArray(item.MeasuredValueSequence)[0];
  if (measured) measured.MeasurementUnitsCodeSequence = [unit];
}

function qualifierItem(type: string): SrItem {
  return {
    RelationshipType: "HAS CONCEPT MOD",
    ValueType: "CODE",
    ConceptNameCodeSequence: [CALIBRATION_QUALIFIER],
    ConceptCodeSequence: [{ CodeValue: type, CodingSchemeDesignator: SCHEME, CodeMeaning: type }],
  };
}

function userCalibrationItem(user: UserCalibration): SrItem {
  const reference: SrItem = { ReferencedSOPClassUID: user.sopClassUid, ReferencedSOPInstanceUID: user.sopInstanceUid };
  if (user.frame !== undefined) reference.ReferencedFrameNumber = user.frame;
  return {
    RelationshipType: "CONTAINS",
    ValueType: "CONTAINER",
    ContinuityOfContent: "SEPARATE",
    ConceptNameCodeSequence: [USER_CALIBRATION],
    ContentSequence: [
      {
        RelationshipType: "CONTAINS",
        ValueType: "NUM",
        ConceptNameCodeSequence: [KNOWN_LENGTH],
        MeasuredValueSequence: [{ MeasurementUnitsCodeSequence: [ucumUnit("mm")], NumericValue: user.knownLengthMm }],
        ContentSequence: [
          {
            RelationshipType: "INFERRED FROM",
            ValueType: "SCOORD",
            GraphicType: "POLYLINE",
            GraphicData: user.line.flat(),
            ContentSequence: [{ RelationshipType: "SELECTED FROM", ValueType: "IMAGE", ReferencedSOPSequence: [reference] }],
          },
        ],
      },
    ],
  };
}

/**
 * Rewrite a generated report's measurement groups (in place): `measurements[i]` describes group i
 * (the adapter emits one group per annotation, in toolState order).
 */
export function annotateReport(dataset: SrItem, measurements: (MeasurementUnits | undefined)[]): void {
  measurementGroups(dataset).forEach((group, i) => {
    const m = measurements[i];
    if (!m) return;
    const content = toArray(group.ContentSequence);
    for (const item of content) {
      if (item.ValueType !== "NUM") continue;
      const dim = dimension(item);
      const raw = dim === "area" ? m.areaUnit ?? (m.unit && `${m.unit.split(" ")[0]}²`) : dim === "length" ? m.unit : undefined;
      const unit = raw && ucumUnit(raw);
      if (unit) setUnit(item, unit);
    }
    const type = m.unit ? calibrationType(m.unit) : "";
    if (type) content.push(qualifierItem(type));
    if (m.user) content.push(userCalibrationItem(m.user));
    group.ContentSequence = content;
  });
}

/** User calibrations stored in a report, one per image (to reapply on reopen). */
export function readUserCalibrations(dataset: SrItem): UserCalibration[] {
  const found = new Map<string, UserCalibration>();
  for (const group of measurementGroups(dataset)) {
    for (const container of toArray(group.ContentSequence).filter((i) => isCode(i, USER_CALIBRATION))) {
      const known = toArray(container.ContentSequence).find((i) => isCode(i, KNOWN_LENGTH));
      const line = toArray(known?.ContentSequence).find((i) => i.ValueType === "SCOORD");
      const reference = toArray(toArray(line?.ContentSequence).find((i) => i.ValueType === "IMAGE")?.ReferencedSOPSequence)[0];
      const data = toArray(line?.GraphicData).map(Number);
      const knownLengthMm = Number(toArray(known?.MeasuredValueSequence)[0]?.NumericValue);
      if (!reference || data.length !== 4 || !(knownLengthMm > 0)) continue;
      const frame = reference.ReferencedFrameNumber;
      const user: UserCalibration = {
        sopClassUid: String(reference.ReferencedSOPClassUID),
        sopInstanceUid: String(reference.ReferencedSOPInstanceUID),
        ...(frame !== undefined ? { frame: Number(frame) } : {}),
        line: [[data[0], data[1]], [data[2], data[3]]],
        knownLengthMm,
      };
      found.set(`${user.sopInstanceUid}:${user.frame ?? 1}`, user);
    }
  }
  return [...found.values()];
}
