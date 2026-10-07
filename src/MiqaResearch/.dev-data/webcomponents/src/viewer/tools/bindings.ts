// Workstation mouse (spec "Chrome, mouse and tools"), as a plan of abstract buttons per tool id.
// Pure: the CS3D adapter turns it into MouseBindings (adapter/cornerstone/tools.ts).
//   left = selected tool · right-drag = W/L (a segment tool: its erase twin) · middle = pan
//   wheel = scroll · Ctrl+wheel = zoom · on WSI: wheel = zoom.
import type { ViewportKind } from "./registry.ts";

export type MouseButton = "primary" | "secondary" | "middle" | "wheel" | "ctrl+wheel";

/** Tool id → buttons that activate it. Tools not in the plan are passive or disabled. */
export type BindingPlan = Record<string, MouseButton[]>;

export interface BindingRequest {
  /** Tool selected in the rail (left button). */
  primary: string;
  viewport: ViewportKind;
  /** Tool for right-drag instead of W/L, e.g. a segment tool's erase twin (#286). */
  secondary?: string;
}

export const NAV_TOOLS = { windowLevel: "WindowLevel", pan: "Pan", zoom: "Zoom", scroll: "StackScroll" } as const;

export function workstationBindings({ primary, viewport, secondary }: BindingRequest): BindingPlan {
  const plan: BindingPlan = {};
  const bind = (tool: string, button: MouseButton) => (plan[tool] ??= []).push(button);
  const wsi = viewport === "wsi";

  bind(primary, "primary");
  if (secondary) bind(secondary, "secondary");
  else if (!wsi) bind(NAV_TOOLS.windowLevel, "secondary");
  bind(NAV_TOOLS.pan, "middle");
  if (wsi) bind(NAV_TOOLS.zoom, "wheel");
  else {
    bind(NAV_TOOLS.scroll, "wheel");
    bind(NAV_TOOLS.zoom, "ctrl+wheel");
  }
  return plan;
}

/** Mouse help lines for the inspector. */
export const MOUSE_HELP: Record<ViewportKind, string[]> = {
  stack: ["Left: selected tool", "Right drag: window/level", "Middle drag: pan", "Wheel: scroll", "Ctrl+wheel: zoom"],
  volume: ["Left: selected tool", "Right drag: window/level", "Middle drag: pan", "Wheel: scroll", "Ctrl+wheel: zoom"],
  wsi: ["Left: selected tool", "Middle drag: pan", "Wheel: zoom"],
};
