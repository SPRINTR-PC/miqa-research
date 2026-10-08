// Annotations (#289), CS3D side: counting edits, SR TID 1500 export with `@cornerstonejs/adapters`
// (then ../../sr.ts for UCUM units, the calibration qualifier and User calibrations), and SR import
// (show a saved head, reapply its User calibrations). CS3D keeps one annotation state for all views.
//
// WSI (spec "Drawing on WSI"): world points are slide mm and go into SCOORD3D (the adapter's 3D path,
// with the slide's base level as the referenced image); freehand contours are simplified
// (Douglas–Peucker, 1 screen pixel at the zoom drawn at); only geometric measurements are stored.
import { Enums, eventTarget, metaData, type RenderingEngine, type Types } from "@cornerstonejs/core";
import { adaptersSR } from "@cornerstonejs/adapters";
import * as csTools from "@cornerstonejs/tools";
import dcmjs from "dcmjs";

import type { DicomJsonInstance, LoadedSeries } from "../../series.ts";
import { simplifyContour, type Point3 } from "../../simplify.ts";
import { EXPORTABLE_TOOLS, annotateReport, readUserCalibrations, type MeasurementUnits, type SrItem } from "../../sr.ts";
import { isWholeSlide } from "../../wsi.ts";
import type { AnnotationSet } from "../adapter.ts";
import { applyUserCalibration, isCalibrationLine, onUserCalibration, userCalibrationOf } from "./calibration.ts";
import { isSegmentationHelper } from "./segmentation.ts";

type Annotation = csTools.Types.Annotation;
type Stats = Record<string, unknown>;

const { MeasurementReport, NO_IMAGE_ID } = adaptersSR.Cornerstone3D;
const COMPREHENSIVE_3D_SR = "1.2.840.10008.5.1.4.1.1.88.34";
const FREEHAND = "PlanarFreehandROI";
/** Measurements kept on WSI: geometric only (intensity stats are NaN on a slide). */
const GEOMETRIC = new Set(["length", "area", "perimeter", "radius", "width", "height", "unit", "areaUnit", "radiusUnit"]);

const TAG = { SOPClassUID: "00080016", SOPInstanceUID: "00080018", FrameOfReferenceUID: "00200052" } as const;
const first = (instance: DicomJsonInstance, tag: string) => String(instance[tag]?.Value?.[0] ?? "");
/** 1-based frame of a `wadors:…/frames/<n>` imageId. */
const frameOf = (imageId: string) => Number(imageId.match(/\/frames\/(\d+)$/)?.[1] ?? 1);

/** WSI: the adapter's 3D (SCOORD3D) path asks a volume for its referenced image; a slide has none. */
class SlideReport extends MeasurementReport {
  static slideImageId = "";
  static getImageIdFromVolume(): string {
    return SlideReport.slideImageId;
  }
}

/** Measurements, ROIs and arrows: not Calibrate lines, not the segment tools' helpers. */
const isAnnotation = (a: Annotation) => !isCalibrationLine(a) && !isSegmentationHelper(a);

/**
 * Annotations on `series`: its images (stack, volume views in the acquired plane), its volume, or
 * on a slide its Frame of Reference (WSI ROIs carry no referenced image).
 */
function annotationsOn(series: LoadedSeries): Annotation[] {
  const images = new Set(series.images.map((im) => im.imageId));
  const uid = series.ref.seriesUid;
  const slideFrameOfReference = isWholeSlide(series) ? first(series.images[0].instance, TAG.FrameOfReferenceUID) : undefined;
  return csTools.annotation.state.getAllAnnotations().filter((a) => {
    if (!isAnnotation(a)) return false;
    const { referencedImageId: ref, volumeId, FrameOfReferenceUID } = a.metadata ?? {};
    if (ref) return images.has(ref);
    if (volumeId) return volumeId.includes(uid);
    return !!slideFrameOfReference && FrameOfReferenceUID === slideFrameOfReference;
  });
}

function statsOf(a: Annotation): Stats {
  const cached = (a.data.cachedStats ?? {}) as Record<string, Stats>;
  const ref = a.metadata?.referencedImageId;
  return (ref && cached[`imageId:${ref}`]) || Object.values(cached)[0] || {};
}

/** Drop NaN/∞ stats (dcmjs would write invalid DS values); on WSI, everything but geometry. */
function cleanStats(stats: Stats, wsi: boolean): Stats {
  return Object.fromEntries(
    Object.entries(stats).filter(([k, v]) => (typeof v !== "number" || Number.isFinite(v)) && (!wsi || GEOMETRIC.has(k))),
  );
}

export function watchAnnotations(engine: RenderingEngine, onChange: () => void): AnnotationSet {
  let revision = 0;
  /** WSI freehand tolerance: world mm per screen pixel at the zoom each contour was drawn at. */
  const tolerance = new Map<string, number>();
  const bump = () => {
    revision += 1;
    onChange();
  };

  const recordTolerance = (a: Annotation) => {
    if (a.metadata?.toolName !== FREEHAND || !a.annotationUID) return;
    const slide = engine.getViewports().find((vp) => vp.type === Enums.ViewportType.WHOLE_SLIDE);
    if (!slide) return;
    const p = slide.canvasToWorld([0, 0]);
    const q = slide.canvasToWorld([1, 0]);
    tolerance.set(a.annotationUID, Math.hypot(q[0] - p[0], q[1] - p[1], q[2] - p[2]));
  };

  const onAnnotation = (e: Event) => {
    const { annotation, changeType } = (e as CustomEvent<{ annotation?: Annotation; changeType?: string }>).detail ?? {};
    if (!annotation || !isAnnotation(annotation)) return;
    // Stats recomputed on render (after import, calibration, …) are not edits.
    if (e.type === csTools.Enums.Events.ANNOTATION_MODIFIED && changeType === csTools.Enums.ChangeTypes.StatsUpdated) return;
    if (e.type === csTools.Enums.Events.ANNOTATION_COMPLETED) recordTolerance(annotation);
    if (e.type === csTools.Enums.Events.ANNOTATION_REMOVED && annotation.annotationUID) tolerance.delete(annotation.annotationUID);
    bump();
  };
  const EVENTS = [
    csTools.Enums.Events.ANNOTATION_COMPLETED,
    csTools.Enums.Events.ANNOTATION_MODIFIED,
    csTools.Enums.Events.ANNOTATION_REMOVED,
  ];
  EVENTS.forEach((ev) => eventTarget.addEventListener(ev, onAnnotation));
  const stopCalibration = onUserCalibration(bump);

  /** A copy for the adapter: clean stats; on WSI the slide as referenced image and simplified contours. */
  const exportCopy = (a: Annotation, slide: { imageId: string; frameOfReference: string } | undefined): Annotation => {
    const ref = a.metadata?.referencedImageId ?? slide?.imageId;
    const wsi = !!slide;
    const cached = (a.data.cachedStats ?? {}) as Record<string, Stats>;
    const cachedStats = ref
      ? { [`imageId:${ref}`]: cleanStats(statsOf(a), wsi) }
      : Object.fromEntries(Object.entries(cached).map(([k, v]) => [k, cleanStats(v, wsi)]));
    const data = { ...a.data, cachedStats } as Annotation["data"] & { contour?: { polyline?: Point3[]; closed?: boolean } };
    const tol = a.annotationUID ? tolerance.get(a.annotationUID) : undefined;
    if (wsi && tol && data.contour?.polyline?.length) {
      data.contour = { ...data.contour, polyline: simplifyContour(data.contour.polyline, tol, !!data.contour.closed) };
    }
    const metadata = {
      ...a.metadata,
      referencedImageId: ref,
      FrameOfReferenceUID: a.metadata?.FrameOfReferenceUID ?? slide?.frameOfReference,
    } as Annotation["metadata"];
    return { ...a, metadata, data };
  };

  /** Raw units and the User calibration of an annotation's image (../../sr.ts rewrites the SR with them). */
  const unitsOf = (a: Annotation, series: LoadedSeries): MeasurementUnits => {
    const stats = statsOf(a);
    const areaUnit = typeof stats.areaUnit === "string" ? stats.areaUnit : undefined;
    const unit = typeof stats.unit === "string" ? stats.unit : areaUnit?.replace("²", "");
    const ref = a.metadata?.referencedImageId;
    const line = ref ? userCalibrationOf(ref) : undefined;
    const image = ref ? series.images.find((im) => im.imageId === ref) : undefined;
    if (!line || !image) return { unit, areaUnit };
    const user = {
      sopClassUid: first(image.instance, TAG.SOPClassUID),
      sopInstanceUid: first(image.instance, TAG.SOPInstanceUID),
      ...(series.images.filter((im) => im.instance === image.instance).length > 1 ? { frame: frameOf(ref!) } : {}),
      ...line,
    };
    return { unit, areaUnit, user };
  };

  return {
    revision: () => revision,
    count: (series) => annotationsOn(series).length,
    toolNames: (series) => annotationsOn(series).map((a) => a.metadata!.toolName),

    async exportSr(series: LoadedSeries): Promise<Blob> {
      const annotations = annotationsOn(series).filter((a) => EXPORTABLE_TOOLS.includes(a.metadata!.toolName));
      if (!annotations.length) throw new Error("no annotations to save");
      const slide = isWholeSlide(series)
        ? {
            imageId: annotations[0].metadata?.referencedImageId ?? series.images[0].imageId,
            frameOfReference: first(series.images[0].instance, TAG.FrameOfReferenceUID),
          }
        : undefined;
      // The adapter emits one measurement group per annotation, in this toolState order.
      const toolState: Record<string, Record<string, { data: Annotation[] }>> = {};
      const units = new Map<Annotation, MeasurementUnits>();
      for (const a of annotations) {
        const key = slide ? NO_IMAGE_ID : (a.metadata?.referencedImageId ?? NO_IMAGE_ID);
        const copy = exportCopy(a, slide);
        units.set(copy, unitsOf(a, series));
        ((toolState[key] ??= {})[a.metadata!.toolName] ??= { data: [] }).data.push(copy);
      }
      const ordered = Object.values(toolState).flatMap((byTool) => Object.values(byTool).flatMap(({ data }) => data));
      let report: { dataset: SrItem };
      if (slide) {
        SlideReport.slideImageId = slide.imageId;
        report = SlideReport.generateReport(toolState, metaData, {});
      } else {
        report = MeasurementReport.generateReport(toolState, metaData, {});
      }
      const dataset = report.dataset;
      annotateReport(dataset, ordered.map((a) => units.get(a)));
      dataset.SOPClassUID = COMPREHENSIVE_3D_SR;
      dataset.Modality = "SR";
      dataset.SeriesDescription = "Annotations";
      return new Blob([dcmjs.data.datasetToDict(dataset).write()], { type: "application/dicom" });
    },

    clear(series: LoadedSeries): void {
      for (const a of annotationsOn(series)) csTools.annotation.state.removeAnnotation(a.annotationUID!);
      engine.getViewports().forEach((vp) => vp.render());
    },

    async importSr(instance: DicomJsonInstance, series: LoadedSeries): Promise<void> {
      const dataset = dcmjs.data.DicomMetaDictionary.naturalizeDataset(structuredClone(instance)) as SrItem;
      const sopFrameToImageId: Record<string, string> = {};
      for (const im of series.images) sopFrameToImageId[`${first(im.instance, TAG.SOPInstanceUID)}:${frameOf(im.imageId)}`] = im.imageId;
      // User calibrations first, so the measurements are drawn with the stored spacing.
      for (const user of readUserCalibrations(dataset)) {
        const imageId = sopFrameToImageId[`${user.sopInstanceUid}:${user.frame ?? 1}`];
        if (imageId) applyUserCalibration(engine, imageId, { line: user.line, knownLengthMm: user.knownLengthMm });
      }
      const frameOfReference = first(series.images[0].instance, TAG.FrameOfReferenceUID);
      const wsi = isWholeSlide(series);
      const byTool = MeasurementReport.generateToolState(dataset, sopFrameToImageId, metaData, undefined) as Record<
        string,
        { annotation: Annotation }[]
      >;
      for (const states of Object.values(byTool)) {
        for (const { annotation } of states) {
          if (wsi) annotation.metadata!.referencedImageId ??= series.images[0].imageId;
          annotation.invalidated = true;
          csTools.annotation.state.addAnnotation(annotation, annotation.metadata?.FrameOfReferenceUID ?? frameOfReference);
        }
      }
      engine.getViewports().forEach((vp: Types.IViewport) => vp.render());
    },

    dispose(): void {
      EVENTS.forEach((ev) => eventTarget.removeEventListener(ev, onAnnotation));
      stopCalibration();
    },
  };
}
