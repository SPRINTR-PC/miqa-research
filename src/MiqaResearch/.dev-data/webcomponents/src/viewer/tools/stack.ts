// #280 tools: navigation, measurements and Arrow (spec tool sets). `viewports` follows the spec:
// stack all; three views/fusion the same (Calibrate excluded, #281/#282); WSI Pan, Zoom, Length,
// ROIs, Arrow. Calibrate (#281), Crosshairs (#282) and segment tools (#286) register in their own modules.
// Keys are taken by the prototype's map: x Crosshairs, c Calibrate, g d k q j y m segment tools.
import { tools } from "./registry.ts";

const ALL = ["stack", "volume", "wsi"] as const;
const PLANAR = ["stack", "volume"] as const;

tools.register({ id: "WindowLevel", label: "Window/Level", key: "w", group: "nav", icon: "◐", viewports: PLANAR });
tools.register({ id: "Pan", label: "Pan", key: "p", group: "nav", icon: "✥", viewports: ALL });
tools.register({ id: "Zoom", label: "Zoom", key: "z", group: "nav", icon: "⌕", viewports: ALL });
tools.register({ id: "StackScroll", label: "Scroll", key: "s", group: "nav", icon: "⇕", viewports: PLANAR });
tools.register({ id: "Length", label: "Length", key: "l", group: "measure", icon: "⟷", viewports: ALL });
tools.register({ id: "Angle", label: "Angle", key: "a", group: "measure", icon: "∠", viewports: PLANAR });
tools.register({ id: "Bidirectional", label: "Bidirectional", key: "b", group: "measure", icon: "✛", viewports: PLANAR });
tools.register({ id: "Probe", label: "Probe", key: "o", group: "measure", icon: "⊙", viewports: PLANAR });
tools.register({ id: "RectangleROI", label: "Rectangle ROI", key: "r", group: "measure", icon: "▭", viewports: ALL });
tools.register({ id: "EllipticalROI", label: "Ellipse ROI", key: "e", group: "measure", icon: "◯", viewports: ALL });
tools.register({ id: "PlanarFreehandROI", label: "Freehand ROI", key: "f", group: "measure", icon: "✎", viewports: ALL });
tools.register({
  id: "ArrowAnnotate",
  label: "Arrow",
  key: "t",
  group: "annotate",
  icon: "➚",
  viewports: ALL,
  annotateOnly: true,
});
