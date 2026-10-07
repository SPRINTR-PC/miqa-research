// Stack view: one STACK viewport showing a series image by image.
// Mouse bindings here are a minimal placeholder; the workstation bindings and tool
// rail are #280's (port `applyBindings` from the prototype's stage.ts).
import { Enums, type RenderingEngine, type Types } from "@cornerstonejs/core";
import * as csTools from "@cornerstonejs/tools";

import type { StackState, StackView, VoiRange } from "../adapter.ts";

const { MouseBindings } = csTools.Enums;

export interface StackHandle extends StackView {
  dispose(): void;
}

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
  for (const [tool, bindings] of [
    [csTools.WindowLevelTool, [{ mouseButton: MouseBindings.Primary }]],
    [csTools.PanTool, [{ mouseButton: MouseBindings.Auxiliary }]],
    [csTools.ZoomTool, [{ mouseButton: MouseBindings.Secondary }]],
    [csTools.StackScrollTool, [{ mouseButton: MouseBindings.Wheel }]],
  ] as const) {
    toolGroup.addTool(tool.toolName);
    toolGroup.setToolActive(tool.toolName, { bindings: [...bindings] });
  }

  const events = [Enums.Events.STACK_NEW_IMAGE, Enums.Events.VOI_MODIFIED, Enums.Events.IMAGE_RENDERED];
  events.forEach((e) => element.addEventListener(e, onChange));

  await viewport.setStack(imageIds, 0);
  viewport.render();

  return {
    state(): StackState {
      const voi = viewport.getProperties().voiRange;
      return {
        imageIndex: viewport.getCurrentImageIdIndex(),
        imageCount: viewport.getImageIds().length,
        voi: voi ? { lower: voi.lower, upper: voi.upper } : undefined,
      };
    },
    scrollTo(imageIndex: number) {
      void viewport.setImageIdIndex(imageIndex);
    },
    setVoi(voi: VoiRange) {
      viewport.setProperties({ voiRange: voi });
      viewport.render();
    },
    dispose() {
      events.forEach((e) => element.removeEventListener(e, onChange));
      csTools.ToolGroupManager.destroyToolGroup(toolGroupId);
    },
  };
}
