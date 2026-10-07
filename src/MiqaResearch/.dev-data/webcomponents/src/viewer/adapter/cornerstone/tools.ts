// CS3D side of the tool registry: tool id (ToolDef.id) → CS3D tool class (+ optional tool-instance
// config), and the workstation binding plan (../../tools/bindings.ts) applied to a tool group.
// Capability modules register their CS3D tools here from their own file, e.g. Calibrate (#281,
// calibration.ts), Crosshairs (#282, volume.ts), segment tools (#286, segmentation.ts):
//   registerCornerstoneTool(MyTool)                                  // id = MyTool.toolName
//   registerCornerstoneTool(csTools.BrushTool, { id: "Eraser", configuration: {...} })  // tool instance
// Always use `Tool.toolName`, never class names (minify mangles them).
import * as csTools from "@cornerstonejs/tools";

import type { BindingPlan, MouseButton } from "../../tools/bindings.ts";

type ToolClass = Parameters<typeof csTools.addTool>[0] & { toolName: string };

interface CornerstoneTool {
  id: string;
  tool: ToolClass;
  configuration?: Record<string, unknown>;
  /** Tools that stay drawn and editable when not on a button (annotations). */
  passive: boolean;
}

const registry = new Map<string, CornerstoneTool>();
let initialised = false;

export function registerCornerstoneTool(
  tool: ToolClass,
  options: { id?: string; configuration?: Record<string, unknown>; passive?: boolean } = {},
): void {
  const id = options.id ?? tool.toolName;
  if (registry.has(id)) throw new Error(`CS3D tool ${id} is already registered`);
  registry.set(id, { id, tool, configuration: options.configuration, passive: options.passive ?? false });
  if (initialised) csTools.addTool(tool); // idempotent per toolName
}

/** Called once from initCornerstone, after csTools.init(). */
export function addRegisteredTools(): void {
  initialised = true;
  registry.forEach(({ tool }) => csTools.addTool(tool));
}

/** Add every registered tool to a tool group (base tools by name, instances with their config). */
export function addToolsToGroup(group: csTools.Types.IToolGroup): void {
  registry.forEach(({ id, tool, configuration }) => {
    if (id === tool.toolName) group.addTool(id, configuration);
    else group.addToolInstance(id, tool.toolName, configuration);
  });
}

export function isRegisteredTool(id: string): boolean {
  return registry.has(id);
}

const { MouseBindings, KeyboardBindings } = csTools.Enums;

function toBindings(button: MouseButton) {
  switch (button) {
    case "primary":
      return [{ mouseButton: MouseBindings.Primary }];
    case "secondary":
      return [{ mouseButton: MouseBindings.Secondary }];
    case "middle":
      return [{ mouseButton: MouseBindings.Auxiliary }];
    case "wheel":
      return [{ mouseButton: MouseBindings.Wheel }];
    case "ctrl+wheel":
      // ⌘ too, so trackpad users on macOS get the same zoom.
      return [
        { mouseButton: MouseBindings.Wheel, modifierKey: KeyboardBindings.Ctrl },
        { mouseButton: MouseBindings.Wheel, modifierKey: KeyboardBindings.Meta },
      ];
  }
}

/**
 * Make `plan` the group's bindings. setToolActive *merges* bindings into an already-active tool,
 * so every tool is disabled first (else a former primary tool keeps the left button).
 * Tools off the plan: annotation tools passive (drawn + editable), the rest disabled.
 */
export function applyBindingPlan(group: csTools.Types.IToolGroup, plan: BindingPlan): void {
  for (const id of Object.keys(plan)) {
    if (!registry.has(id)) throw new Error(`Unknown tool ${id}`);
  }
  registry.forEach(({ id, passive }) => {
    group.setToolDisabled(id);
    const buttons = plan[id];
    if (buttons) group.setToolActive(id, { bindings: buttons.flatMap(toBindings) });
    else if (passive) group.setToolPassive(id);
  });
}

// #280: navigation, measurement and Arrow tools.
const T = csTools;
[T.WindowLevelTool, T.PanTool, T.ZoomTool, T.StackScrollTool].forEach((tool) => registerCornerstoneTool(tool));
[
  T.LengthTool,
  T.AngleTool,
  T.BidirectionalTool,
  T.ProbeTool,
  T.RectangleROITool,
  T.EllipticalROITool,
  T.PlanarFreehandROITool,
  T.ArrowAnnotateTool,
].forEach((tool) => registerCornerstoneTool(tool, { passive: true }));
