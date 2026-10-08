// Segmentation (#286), CS3D side: the segment tools (and their erase twins) and the labelmap.
// The labelmap is one derived Uint8 image per base image (`createAndCacheDerivedLabelmapImages`), so a
// stack shows it directly and a volume view gets an image-backed labelmap volume over the same images
// (CS3D creates it on demand): painting in either shows in both. Threshold: CS3D's
// `rectangleROIThresholdVolumeByRange` on volumes (any layer's volume); on a stack our own fill
// (../../segmentation.ts), since the helper is volume-only. Polygon: a linear SplineROI rasterised into
// the labelmap when closed.
import { cache, eventTarget, imageLoader, metaData, utilities, type RenderingEngine, type Types } from "@cornerstonejs/core";
import { adaptersSEG } from "@cornerstonejs/adapters";
import * as csTools from "@cornerstonejs/tools";
import dcmjs from "dcmjs";

import {
  DEFAULT_BRUSH_SIZE,
  SegmentList,
  polygonPixels,
  thresholdPixels,
  type Rgb,
  type SegmentationState,
  type ValueRange,
} from "../../segmentation.ts";
import type { SavedSegmentation } from "../../saved-seg.ts";
import type { LoadedSeries } from "../../series.ts";
import { ERASER, POLYGON, POLYGON_ERASE, THRESHOLD } from "../../tools/segmentation.ts";
import type { SegmentationView, ThresholdOptions, ViewControls } from "../adapter.ts";
import { registerCornerstoneTool } from "./tools.ts";
import { volumeIdFor } from "./volume.ts";

const T = csTools;
const S = csTools.segmentation;
const LABELMAP = T.Enums.SegmentationRepresentations.Labelmap;

// Tools. Scissors and the brush paint the active segment; their erase twins (right-drag) erase.
registerCornerstoneTool(T.BrushTool);
registerCornerstoneTool(T.BrushTool, { id: ERASER, configuration: { activeStrategy: "ERASE_INSIDE_CIRCLE" } });
for (const tool of [T.RectangleScissorsTool, T.CircleScissorsTool, T.SphereScissorsTool]) {
  registerCornerstoneTool(tool);
  registerCornerstoneTool(tool, { id: `${tool.toolName}Erase`, configuration: { activeStrategy: "ERASE_INSIDE" } });
}
// Rectangles stay drawn (passive) until the threshold runs.
registerCornerstoneTool(T.RectangleROIThresholdTool, { passive: true });
const polygon = { calculateStats: false, spline: { type: "LINEAR", drawPreviewEnabled: true } };
registerCornerstoneTool(T.SplineROITool, { id: POLYGON, configuration: polygon });
registerCornerstoneTool(T.SplineROITool, { id: POLYGON_ERASE, configuration: polygon });

/** Helper annotations of the segment tools: not measurements (stack annotationCount, Save #289). */
export function isSegmentationHelper(annotation: csTools.Types.Annotation): boolean {
  const tool = annotation.metadata?.toolName;
  return tool === THRESHOLD || tool === POLYGON || tool === POLYGON_ERASE;
}

/** Viewports a view shows, and whether they are a stack (own threshold fill) or volume views. */
export interface ShownViewports {
  kind: "stack" | "volume";
  viewportIds: string[];
}

type Point = Types.Point3;

/** SEG segment description (SegmentSequence item): manual, coded as tissue, with its display colour. */
function segmentMetadata(index: number, label: string, color: Rgb) {
  const tissue = { CodeValue: "85756007", CodingSchemeDesignator: "SCT", CodeMeaning: "Tissue" };
  return {
    SegmentNumber: index,
    SegmentLabel: label,
    SegmentAlgorithmType: "MANUAL",
    RecommendedDisplayCIELabValue: dcmjs.data.Colors.rgb2DICOMLAB(color.map((c) => c / 255)).map(Math.round),
    SegmentedPropertyCategoryCodeSequence: tissue,
    SegmentedPropertyTypeCodeSequence: tissue,
  };
}

/**
 * A saved SEG (#290) into the labelmap images (one per base image) and the segment list. CS3D's reader takes
 * the served header as the multiframe and our fetched frames (bit-packed BINARY is unpacked by it); its own
 * labelmap images are copied, then dropped from the cache.
 */
async function readSavedSeg(saved: SavedSegmentation, imageIds: string[], labelmapIds: string[], list: SegmentList): Promise<void> {
  const dataset = dcmjs.data.DicomMetaDictionary.naturalizeDataset(structuredClone(saved.instance));
  const multiframe = dcmjs.normalizers.Normalizer.normalizeToDataset([dataset]);
  const segImageId = `mires-seg:${String(dataset.SOPInstanceUID ?? "")}`;
  const result = await adaptersSEG.Cornerstone3D.Segmentation.createLabelmapsFromSegImageIds(imageIds, segImageId, metaData, {
    multiframe,
    frameImageIds: saved.frames.map((_, i) => `${segImageId}/frames/${i + 1}`),
    decodeImageData: async (_frameImageId: string, frameNumber: number) => saved.frames[frameNumber - 1],
  });
  // Overlapping segments come as several labelmap layers; later layers win where they overlap.
  const layers = result.labelMapImages as Types.IImage[][];
  for (const layer of layers) {
    layer.forEach((image, k) => {
      const source = image?.voxelManager?.getScalarData() as ArrayLike<number> | undefined;
      const target = cache.getImage(labelmapIds[k])?.voxelManager as Types.IVoxelManager<number> | undefined;
      if (!source || !target) return;
      for (let i = 0; i < source.length; i++) if (source[i]) target.setAtIndex(i, source[i]);
    });
    layer.forEach((image) => image && cache.removeImageLoadObject(image.imageId, { force: true }));
  }
  type SegmentItem = { SegmentLabel?: string; RecommendedDisplayCIELabValue?: number[] };
  const segments = (result.segMetadata.data as (SegmentItem | undefined)[]).flatMap((item, index) => (item && index > 0 ? [{ index, item }] : []));
  for (const { index, item } of segments) {
    while (Math.max(...list.segments.map((s) => s.index)) < index) list.add();
    if (item.SegmentLabel) list.rename(index, item.SegmentLabel);
    const lab = item.RecommendedDisplayCIELabValue;
    if (lab?.length === 3) list.setColor(index, dcmjs.data.Colors.dicomlab2RGB(lab.map(Number)).map((c) => Math.round(c * 255)) as Rgb);
  }
  if (segments.length) list.setActive(segments[0].index);
}

export async function createSegmentation(
  engine: RenderingEngine,
  imageIds: string[],
  series: LoadedSeries,
  id: string,
  onChange: () => void,
  viewportsOf: (view: ViewControls) => ShownViewports | undefined,
  saved?: SavedSegmentation,
): Promise<SegmentationView> {
  // Throws CS3D's cache error when the labelmap doesn't fit (the element shows "too large").
  const labelmapIds = imageLoader.createAndCacheDerivedLabelmapImages(imageIds).map((image) => image.imageId);
  const baseIndex = new Map(imageIds.map((imageId, i) => [imageId, i]));
  const list = new SegmentList();
  if (saved) {
    try {
      await readSavedSeg(saved, imageIds, labelmapIds, list);
    } catch (e) {
      labelmapIds.forEach((imageId) => cache.removeImageLoadObject(imageId, { force: true }));
      throw e;
    }
  }
  let brushSize = DEFAULT_BRUSH_SIZE;
  let shown: ShownViewports | undefined;
  /** Edits (#289): painting, threshold, polygon fill, segments added / renamed / recoloured. */
  let revision = 0;

  S.addSegmentations([{ segmentationId: id, representation: { type: LABELMAP, data: { imageIds: labelmapIds } } }]);

  const toolGroups = () =>
    [...new Set((shown?.viewportIds ?? []).map((vp) => T.ToolGroupManager.getToolGroupForViewport(vp, engine.id)?.id))].filter(
      (g): g is string => !!g,
    );

  /** Segment labels and colours into CS3D (labels go into the SEG on save, #289). */
  const sync = () => {
    const segmentation = S.state.getSegmentation(id);
    if (segmentation) {
      segmentation.segments = Object.fromEntries(
        list.segments.map((s) => [
          s.index,
          { segmentIndex: s.index, label: s.label, locked: false, cachedStats: {}, active: s.index === list.active },
        ]),
      );
    }
    S.segmentIndex.setActiveSegmentIndex(id, list.active);
    for (const vp of shown?.viewportIds ?? []) {
      for (const s of list.segments) S.config.color.setSegmentIndexColor(vp, id, s.index, [...s.color, 255] as Types.Color);
    }
    toolGroups().forEach((g) => T.utilities.segmentation.setBrushSizeForToolGroup(g, brushSize));
    T.utilities.segmentation.triggerSegmentationRender();
    onChange();
  };

  const modified = () => {
    revision += 1;
    S.triggerSegmentationEvents.triggerSegmentationDataModified(id);
    T.utilities.segmentation.triggerSegmentationRender();
    onChange();
  };

  const labelmapImage = (baseImageId: string) => {
    const k = baseIndex.get(baseImageId);
    return k === undefined ? undefined : cache.getImage(labelmapIds[k]);
  };

  /** Rasterise a closed polygon into the labelmap on its plane: the active segment, or erase it (value 0). */
  const fillPolygon = (annotation: csTools.Types.Annotation, value: number) => {
    const data = annotation.data as { contour?: { polyline?: Point[] }; handles: { points: Point[] } };
    const points = data.contour?.polyline?.length ? data.contour.polyline : data.handles.points;
    T.annotation.state.removeAnnotation(annotation.annotationUID!);
    const set = (vm: Types.IVoxelManager<number>, i: number) => {
      if (value || vm.getAtIndex(i) === list.active) vm.setAtIndex(i, value);
    };
    const refId = annotation.metadata?.referencedImageId;
    const image = refId ? labelmapImage(refId) : undefined;
    if (refId && image) {
      // In an image's plane (stack, or a volume view in the acquired plane).
      const poly = points.map((p) => utilities.worldToImageCoords(refId, p) as [number, number]);
      const vm = image.voxelManager as Types.IVoxelManager<number>;
      polygonPixels(poly, image.columns, image.rows).forEach((i) => set(vm, i));
    } else {
      // A volume view in another orientation: axis-aligned planes of the labelmap volume only.
      const volume = T.utilities.segmentation.getOrCreateSegmentationVolume(id);
      if (!volume) return;
      const ijk = points.map((p) => volume.imageData!.worldToIndex(p) as number[]);
      const spans = [0, 1, 2].map((ax) => Math.max(...ijk.map((p) => p[ax])) - Math.min(...ijk.map((p) => p[ax])));
      const normal = spans.indexOf(Math.min(...spans));
      if (spans[normal] > 1) return; // oblique plane
      const [u, v] = [0, 1, 2].filter((ax) => ax !== normal);
      const k = Math.round(ijk.reduce((sum, p) => sum + p[normal], 0) / ijk.length);
      const dims = volume.dimensions;
      const strides = [1, dims[0], dims[0] * dims[1]];
      // Index coordinates are voxel centres; polygonPixels takes corner-based coordinates.
      const poly = ijk.map((p) => [p[u] + 0.5, p[v] + 0.5] as [number, number]);
      const vm = volume.voxelManager as Types.IVoxelManager<number>;
      polygonPixels(poly, dims[u], dims[v]).forEach((i) =>
        set(vm, (i % dims[u]) * strides[u] + Math.floor(i / dims[u]) * strides[v] + k * strides[normal]),
      );
    }
    modified();
  };

  const thresholdAnnotations = () =>
    T.annotation.state.getAllAnnotations().filter((a) => a.metadata?.toolName === THRESHOLD);

  const onAnnotation = (e: Event) => {
    const annotation = (e as CustomEvent<{ annotation?: csTools.Types.Annotation }>).detail?.annotation;
    const tool = annotation?.metadata?.toolName;
    if (annotation && e.type === T.Enums.Events.ANNOTATION_COMPLETED && (tool === POLYGON || tool === POLYGON_ERASE)) {
      fillPolygon(annotation, tool === POLYGON ? list.active : 0);
    } else if (tool === THRESHOLD) onChange();
  };
  const onDataModified = (e: Event) => {
    if ((e as CustomEvent<{ segmentationId: string }>).detail?.segmentationId !== id) return;
    revision += 1;
    onChange();
  };
  const ANNOTATION_EVENTS = [T.Enums.Events.ANNOTATION_COMPLETED, T.Enums.Events.ANNOTATION_REMOVED];
  ANNOTATION_EVENTS.forEach((ev) => eventTarget.addEventListener(ev, onAnnotation));
  eventTarget.addEventListener(T.Enums.Events.SEGMENTATION_DATA_MODIFIED, onDataModified);

  const voxelCounts = () => {
    const counts: Record<number, number> = {};
    for (const imageId of labelmapIds) {
      const data = cache.getImage(imageId)?.voxelManager?.getScalarData() as ArrayLike<number> | undefined;
      if (!data) continue;
      for (let i = 0; i < data.length; i++) if (data[i]) counts[data[i]] = (counts[data[i]] ?? 0) + 1;
    }
    return counts;
  };

  /** Stack threshold: per image, our own fill (CS3D's helper is volume-only). */
  const thresholdStack = (annotations: csTools.Types.Annotation[], range: ValueRange, slices: number) => {
    for (const a of annotations) {
      const refId = a.metadata?.referencedImageId;
      const k0 = refId ? baseIndex.get(refId) : undefined;
      if (refId === undefined || k0 === undefined) continue;
      const corners = (a.data.handles!.points as Point[]).map((p) => utilities.worldToImageCoords(refId, p) as [number, number]);
      const xs = corners.map((c) => c[0]);
      const ys = corners.map((c) => c[1]);
      const rect: [[number, number], [number, number]] = [[Math.min(...xs), Math.min(...ys)], [Math.max(...xs), Math.max(...ys)]];
      for (let k = Math.max(0, k0 - slices); k <= Math.min(imageIds.length - 1, k0 + slices); k++) {
        const image = cache.getImage(imageIds[k]);
        const labels = cache.getImage(labelmapIds[k]);
        if (!image || !labels) continue; // not loaded yet
        // Modality units: pre-scaled by the loader, else apply the rescale here.
        let values = image.voxelManager!.getScalarData() as ArrayLike<number>;
        const { slope = 1, intercept = 0 } = image;
        if (!image.preScale?.scaled && (slope !== 1 || intercept !== 0)) values = Float32Array.from(values, (v) => v * slope + intercept);
        const vm = labels.voxelManager as Types.IVoxelManager<number>;
        thresholdPixels(values, image.columns, rect, range).forEach((i) => vm.setAtIndex(i, list.active));
      }
    }
  };

  return {
    id,
    state(): SegmentationState {
      return {
        segments: list.segments.map((s) => ({ ...s, color: [...s.color] as Rgb })),
        active: list.active,
        brushSize,
        thresholdRectangles: thresholdAnnotations().length,
      };
    },
    async show(view: ViewControls) {
      shown = viewportsOf(view);
      if (!shown) return;
      const missing = shown.viewportIds.filter((vp) => !S.state.getSegmentationRepresentations(vp, { segmentationId: id })?.length);
      if (missing.length) {
        await S.addLabelmapRepresentationToViewportMap(Object.fromEntries(missing.map((vp) => [vp, [{ segmentationId: id }]])));
      }
      shown.viewportIds.forEach((vp) => S.activeSegmentation.setActiveSegmentation(vp, id));
      sync();
    },
    addSegment() {
      list.add();
      revision += 1;
      sync();
    },
    renameSegment(index: number, label: string) {
      list.rename(index, label);
      revision += 1;
      sync();
    },
    setSegmentColor(index: number, color: Rgb) {
      list.setColor(index, color);
      revision += 1;
      sync();
    },
    setActiveSegment(index: number) {
      list.setActive(index);
      sync();
    },
    setBrushSize(size: number) {
      brushSize = size;
      sync();
    },
    threshold(range: ValueRange, { slices, sourceSeriesUid }: ThresholdOptions): number {
      const annotations = thresholdAnnotations();
      if (!annotations.length || !shown) return 0;
      const before = voxelCounts()[list.active] ?? 0;
      if (shown.kind === "stack") thresholdStack(annotations, range, slices);
      else {
        const segmentationVolume = T.utilities.segmentation.getOrCreateSegmentationVolume(id);
        const source = cache.getVolume(volumeIdFor(sourceSeriesUid ?? series.ref.seriesUid));
        if (!segmentationVolume || !source) return 0;
        T.utilities.segmentation.rectangleROIThresholdVolumeByRange(
          annotations.map((a) => a.annotationUID!),
          segmentationVolume,
          [{ volume: source, lower: range.lower, upper: range.upper }],
          { segmentationId: id, segmentIndex: list.active, overwrite: false, numSlicesToProject: slices },
        );
      }
      annotations.forEach((a) => T.annotation.state.removeAnnotation(a.annotationUID!));
      T.utilities.triggerAnnotationRenderForViewportIds(shown.viewportIds);
      modified();
      return (voxelCounts()[list.active] ?? 0) - before;
    },
    voxelCounts,
    revision: () => revision,
    async exportSeg(): Promise<Blob> {
      sync(); // labels and colours as shown
      // Frames of the images in cache (a stack paints only images it has shown), labelmap per base image.
      const frames = imageIds.map((imageId, k) => ({ image: cache.getImage(imageId), labels: cache.getImage(labelmapIds[k]) })).filter(
        (f): f is { image: Types.IImage; labels: Types.IImage } => !!f.image && !!f.labels,
      );
      const labelmaps2D = frames.map(({ labels }) => {
        const pixelData = labels.voxelManager!.getScalarData() as ArrayLike<number>;
        const segments = new Set<number>();
        for (let i = 0; i < pixelData.length; i++) if (pixelData[i]) segments.add(pixelData[i]);
        return { segmentsOnLabelmap: [...segments], pixelData, rows: labels.rows, columns: labels.columns };
      });
      const painted = [...new Set(labelmaps2D.flatMap((l) => l.segmentsOnLabelmap))].sort((a, b) => a - b);
      if (!painted.length) throw new Error("nothing is painted");
      const metadata: unknown[] = [];
      for (const index of painted) {
        const segment = list.segments.find((s) => s.index === index);
        metadata[index] = segmentMetadata(index, segment?.label ?? `Segment ${index}`, segment?.color ?? [255, 0, 0]);
      }
      const seg = adaptersSEG.Cornerstone3D.Segmentation.generateSegmentation(
        frames.map((f) => f.image),
        { segmentsOnLabelmap: painted, metadata, labelmaps2D },
        metaData,
        { SeriesDescription: "Segmentation" },
      );
      return new Blob([dcmjs.data.datasetToDict(seg.dataset).write()], { type: "application/dicom" });
    },
    close() {
      ANNOTATION_EVENTS.forEach((ev) => eventTarget.removeEventListener(ev, onAnnotation));
      eventTarget.removeEventListener(T.Enums.Events.SEGMENTATION_DATA_MODIFIED, onDataModified);
      S.removeSegmentation(id);
      labelmapIds.forEach((imageId) => cache.removeImageLoadObject(imageId, { force: true }));
      shown = undefined;
    },
  };
}
