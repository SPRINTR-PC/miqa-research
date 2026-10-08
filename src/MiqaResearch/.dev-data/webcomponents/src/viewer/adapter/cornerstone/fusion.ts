// Fusion (#284), CS3D side: the overlay W/L tool and per-layer display properties.
// CS3D's WindowLevelTool only windows a fused viewport's first volume, so the selected overlay gets
// its own right-drag tool (LayerWindowLevel); volume.ts binds it as the secondary button and says
// which layer it windows per viewport (`setLayerWindowHandler`).
import { getEnabledElement } from "@cornerstonejs/core";
import * as csTools from "@cornerstonejs/tools";

import type { LayerDisplay } from "../../fusion.ts";
import { registerCornerstoneTool } from "./tools.ts";

type DragHandler = (dx: number, dy: number) => void;

/** viewportId → what a right-drag there does (window the selected overlay). */
const handlers = new Map<string, DragHandler>();

export function setLayerWindowHandler(viewportId: string, handler: DragHandler | undefined): void {
  if (handler) handlers.set(viewportId, handler);
  else handlers.delete(viewportId);
}

interface DragEvent {
  detail: { element: HTMLDivElement; deltaPoints: { canvas: [number, number] } };
}

export class LayerWindowLevelTool extends csTools.BaseTool {
  static toolName = "LayerWindowLevel";

  constructor(toolProps = {}, defaultToolProps = { supportedInteractionTypes: ["Mouse", "Touch"] }) {
    super(toolProps as never, defaultToolProps as never);
  }

  mouseDragCallback(evt: DragEvent): void {
    const { element, deltaPoints } = evt.detail;
    const viewportId = getEnabledElement(element)?.viewport.id;
    if (viewportId) handlers.get(viewportId)?.(deltaPoints.canvas[0], deltaPoints.canvas[1]);
  }

  touchDragCallback(evt: DragEvent): void {
    this.mouseDragCallback(evt);
  }
}

export const LAYER_WINDOW_LEVEL = LayerWindowLevelTool.toolName;

registerCornerstoneTool(LayerWindowLevelTool as never);

/**
 * CS3D colormap properties of a layer: a vtk.js preset by name, the overall opacity multiplier and the
 * opacity transfer curve (`opacityMapping`, data units; an empty curve = flat opacity).
 */
export function colormapProperties({ colormap, opacity, curve }: LayerDisplay) {
  return { name: colormap, opacity, opacityMapping: curve.map((p) => ({ ...p })) };
}
