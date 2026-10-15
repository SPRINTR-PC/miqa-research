// User spacing calibration (#281): the Calibrate tool draws a line; once the user gives its known
// length, `calibrateImageSpacing` (type User) recalibrates that image for the session. Each image's
// reference line and known length are kept, so Save stores them in the SR and reopening reapplies them (#289).
import { Enums, eventTarget, utilities, type RenderingEngine, type Types } from "@cornerstonejs/core";
import * as csTools from "@cornerstonejs/tools";

import type { PendingCalibration } from "../adapter.ts";
import { registerCornerstoneTool } from "./tools.ts";

/** A Length line whose only job is to be told its true length. */
export class CalibrateTool extends csTools.LengthTool {
  static toolName = "Calibrate";
}

// Not passive: the line is removed once applied or cancelled.
registerCornerstoneTool(CalibrateTool);

type Annotation = csTools.Types.Annotation;

/** A User calibration of one image: reference line in DICOM image coordinates (column, row; pixel centres at .5). */
export interface UserLine {
  line: [[number, number], [number, number]];
  knownLengthMm: number;
}

const userLines = new Map<string, UserLine>();
const userCalibrationListeners = new Set<() => void>();

/** The User calibration of `imageId` this session, if any. */
export function userCalibrationOf(imageId: string): UserLine | undefined {
  return userLines.get(imageId);
}

/** Called after every User calibration (Save counts it as an edit). */
export function onUserCalibration(listener: () => void): () => void {
  userCalibrationListeners.add(listener);
  return () => userCalibrationListeners.delete(listener);
}

/** Calibrate `imageId` so `calibration.line` is `knownLengthMm` long (isotropic), and remember it. */
export function applyUserCalibration(engine: RenderingEngine, imageId: string, calibration: UserLine): void {
  const [[c0, r0], [c1, r1]] = calibration.line;
  const pixelsPerMm = Math.hypot(c1 - c0, r1 - r0) / calibration.knownLengthMm;
  if (!(pixelsPerMm > 0) || !Number.isFinite(pixelsPerMm)) return;
  // CS3D's unit function takes x scale from `scale` but y from `scale / rowPixelSpacing`:
  // spacing 1 keeps both equal (isotropic user calibration).
  csTools.utilities.calibrateImageSpacing(imageId, engine, {
    type: Enums.CalibrationTypes.USER,
    scale: pixelsPerMm,
    rowPixelSpacing: 1,
    columnPixelSpacing: 1,
  });
  userLines.set(imageId, calibration);
  userCalibrationListeners.forEach((listener) => listener());
}

export interface CalibrationHandle {
  pending(): PendingCalibration | undefined;
  /** Calibrate the pending line's image so the line is `knownLengthMm` long. */
  calibrate(knownLengthMm: number): void;
  cancel(): void;
  dispose(): void;
}

export function isCalibrationLine(annotation: Annotation): boolean {
  return annotation.metadata?.toolName === CalibrateTool.toolName;
}

/** Watches Calibrate lines drawn on `viewport`'s images; `onChange` fires when the pending line changes. */
export function watchCalibration(
  engine: RenderingEngine,
  viewport: Types.IStackViewport,
  onChange: () => void,
): CalibrationHandle {
  const ownImages = new Set(viewport.getImageIds());
  let line: Annotation | undefined;

  const drop = () => {
    if (line?.annotationUID) csTools.annotation.state.removeAnnotation(line.annotationUID);
    line = undefined;
    viewport.render();
  };

  const onCompleted = (evt: Event) => {
    const { annotation } = (evt as CustomEvent<{ annotation: Annotation }>).detail;
    if (!isCalibrationLine(annotation) || !ownImages.has(annotation.metadata?.referencedImageId ?? "")) return;
    if (line && line !== annotation) drop();
    line = annotation;
    onChange();
  };
  eventTarget.addEventListener(csTools.Enums.Events.ANNOTATION_COMPLETED, onCompleted);

  /** End points of a line in image pixels (index space). */
  const indexPoints = (a: Annotation) => {
    const { imageData } = viewport.getImageData();
    return a.data.handles!.points!.map((point) => utilities.transformWorldToIndex(imageData, point));
  };

  return {
    pending() {
      if (!line) return undefined;
      // Measured as the Length tool would, from the final handles (cachedStats can lag the last drag step).
      const [p, q] = indexPoints(line);
      const { unit, scale, scaleY } = csTools.utilities.getCalibratedLengthUnitsAndScale(viewport.getImageData(), [p, q]);
      return { length: Math.hypot((q[0] - p[0]) / scale, (q[1] - p[1]) / (scaleY || scale)), unit };
    },
    calibrate(knownLengthMm: number) {
      if (!line || !(knownLengthMm > 0)) return;
      const imageId = line.metadata!.referencedImageId!;
      // Index space has pixel centres at integers; DICOM image coordinates at .5.
      const [p, q] = indexPoints(line).map((point) => [point[0] + 0.5, point[1] + 0.5] as [number, number]);
      drop();
      applyUserCalibration(engine, imageId, { line: [p, q], knownLengthMm });
      onChange();
    },
    cancel() {
      drop();
      onChange();
    },
    dispose() {
      eventTarget.removeEventListener(csTools.Enums.Events.ANNOTATION_COMPLETED, onCompleted);
    },
  };
}
