// User spacing calibration (#281): the Calibrate tool draws a line; once the user gives its known
// length, `calibrateImageSpacing` (type User) recalibrates that image for the session.
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
  /** Line length in image pixels, independent of the current calibration. */
  const pixelLength = (a: Annotation) => {
    const [p, q] = indexPoints(a);
    return Math.hypot(q[0] - p[0], q[1] - p[1]);
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
      const pixelsPerMm = pixelLength(line) / knownLengthMm;
      drop();
      if (!(pixelsPerMm > 0)) return onChange();
      // CS3D's unit function takes x scale from `scale` but y from `scale / rowPixelSpacing`:
      // spacing 1 keeps both equal (isotropic user calibration).
      csTools.utilities.calibrateImageSpacing(imageId, engine, {
        type: Enums.CalibrationTypes.USER,
        scale: pixelsPerMm,
        rowPixelSpacing: 1,
        columnPixelSpacing: 1,
      });
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
