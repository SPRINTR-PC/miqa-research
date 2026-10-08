// Stack view: one STACK viewport showing a series image by image, with the workstation mouse
// (../../tools/bindings.ts) on a tool group holding every registered CS3D tool (./tools.ts).
import { Enums, eventTarget, type RenderingEngine, type Types } from "@cornerstonejs/core";
import * as csTools from "@cornerstonejs/tools";

import { workstationBindings } from "../../tools/bindings.ts";
import type { StackState, StackView, VoiRange } from "../adapter.ts";
import { addToolsToGroup, applyBindingPlan } from "./tools.ts";

export interface StackHandle extends StackView {
  dispose(): void;
}

const ELEMENT_EVENTS = [
  Enums.Events.STACK_NEW_IMAGE,
  Enums.Events.VOI_MODIFIED,
  Enums.Events.IMAGE_RENDERED,
  Enums.Events.CAMERA_MODIFIED,
];
const ANNOTATION_EVENTS = [
  csTools.Enums.Events.ANNOTATION_COMPLETED,
  csTools.Enums.Events.ANNOTATION_REMOVED,
];

export async function createStackView(
  engine: RenderingEngine,
  element: HTMLDivElement,
  imageIds: string[],
  onChange: () => void,
): Promise<StackHandle> {
  const viewportId = `stack-${engine.id}`;
  engine.enableElement({ viewportId, type: Enums.ViewportType.STACK, element });
  const viewport = engine.getViewport(viewportId) as Types.IStackViewport;

  const toolGroupId = `tg-${viewportId}`;
  const toolGroup = csTools.ToolGroupManager.createToolGroup(toolGroupId)!;
  toolGroup.addViewport(viewportId, engine.id);
  addToolsToGroup(toolGroup);
  let activeTool = "";
  const setTool = (toolId: string) => {
    applyBindingPlan(toolGroup, workstationBindings({ primary: toolId, viewport: "stack" }));
    activeTool = toolId;
    onChange();
  };

  ELEMENT_EVENTS.forEach((e) => element.addEventListener(e, onChange));
  ANNOTATION_EVENTS.forEach((e) => eventTarget.addEventListener(e, onChange));

  await viewport.setStack(imageIds, 0);
  viewport.render();

  const ownImages = new Set(imageIds);
  const annotationCount = () =>
    csTools.annotation.state
      .getAllAnnotations()
      .filter((a) => ownImages.has(a.metadata?.referencedImageId ?? "")).length;
  const unit = () => {
    // Same image data the measurement tools use (hasPixelSpacing + calibration).
    const imageData = viewport.getImageData();
    return imageData ? csTools.utilities.getCalibratedLengthUnitsAndScale(imageData, []).unit : "";
  };

  return {
    state(): StackState {
      const { voiRange: voi, invert } = viewport.getProperties();
      const [x, y] = viewport.getPan();
      return {
        imageIndex: viewport.getCurrentImageIdIndex(),
        imageCount: viewport.getImageIds().length,
        voi: voi ? { lower: voi.lower, upper: voi.upper } : undefined,
        activeTool,
        invert: !!invert,
        zoom: viewport.getZoom(),
        pan: [x, y],
        unit: unit(),
        annotationCount: annotationCount(),
      };
    },
    scrollTo(imageIndex: number) {
      void viewport.setImageIdIndex(imageIndex);
    },
    setTool,
    setVoi(voi: VoiRange) {
      viewport.setProperties({ voiRange: voi });
      viewport.render();
    },
    resetVoi() {
      // resetProperties also resets invert: keep it, only the window goes back to the image's own.
      const { invert } = viewport.getProperties();
      viewport.resetProperties();
      viewport.setProperties({ invert });
      viewport.render();
      onChange();
    },
    toggleInvert() {
      viewport.setProperties({ invert: !viewport.getProperties().invert });
      viewport.render();
      onChange();
    },
    resetView() {
      viewport.resetCamera();
      viewport.resetProperties();
      viewport.render();
      onChange();
    },
    dispose() {
      ELEMENT_EVENTS.forEach((e) => element.removeEventListener(e, onChange));
      ANNOTATION_EVENTS.forEach((e) => eventTarget.removeEventListener(e, onChange));
      csTools.ToolGroupManager.destroyToolGroup(toolGroupId);
      engine.disableElement(viewportId);
    },
  };
}
