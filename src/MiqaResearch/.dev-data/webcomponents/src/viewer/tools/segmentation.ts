// #286 segment tools: Brush, Eraser, polygon, Rectangle/Circle/Sphere scissors, Rectangle ROI threshold.
// Annotate roles only; stacks and volumes (not WSI, not reduced 3D). With a segment tool selected,
// right-drag erases with the same shape (its erase twin). CS3D side: adapter/cornerstone/segmentation.ts.
import { workstationBindings, type BindingPlan, type BindingRequest } from "./bindings.ts";
import { tools, type ToolDef } from "./registry.ts";

export const BRUSH = "Brush";
export const ERASER = "Eraser";
/** Polygon: a linear SplineROI instance, rasterised into the labelmap when closed. */
export const POLYGON = "PolygonSeg";
export const POLYGON_ERASE = "PolygonSegErase";
export const THRESHOLD = "RectangleROIThreshold";

const segmentTool = (id: string, label: string, key: string, icon: string): ToolDef => ({
  id,
  label,
  key,
  icon,
  group: "segment",
  viewports: ["stack", "volume"],
  annotateOnly: true,
});

export const SEGMENT_TOOLS: ToolDef[] = [
  segmentTool(BRUSH, "Brush", "g", "🖌"),
  segmentTool(ERASER, "Eraser", "d", "⌫"),
  segmentTool(POLYGON, "Polygon (click vertices; double-click or click the first one to close)", "k", "⬠"),
  segmentTool("RectangleScissor", "Rectangle scissors", "q", "⬚"),
  segmentTool("CircleScissor", "Circle scissors", "j", "◌"),
  segmentTool("SphereScissor", "Sphere scissors", "y", "⬤"),
  segmentTool(THRESHOLD, "Rectangle ROI threshold", "m", "▦"),
];
SEGMENT_TOOLS.forEach((t) => tools.register(t));

/** Right-drag twin of a segment tool: the same shape, erasing. */
const ERASE_TWIN: Record<string, string> = {
  [BRUSH]: ERASER,
  [POLYGON]: POLYGON_ERASE,
  RectangleScissor: "RectangleScissorErase",
  CircleScissor: "CircleScissorErase",
  SphereScissor: "SphereScissorErase",
};

export function eraseTwin(toolId: string): string | undefined {
  return ERASE_TWIN[toolId];
}

export function isSegmentTool(toolId: string): boolean {
  return SEGMENT_TOOLS.some((t) => t.id === toolId);
}

/** The workstation mouse, with a segment tool's erase twin on the right button. */
export function segmentBindings(request: BindingRequest): BindingPlan {
  return workstationBindings({ ...request, secondary: request.secondary ?? eraseTwin(request.primary) });
}
