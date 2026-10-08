// Inspector panels. One import line per panel module (calibration legend #281, layout #282,
// layers #284, segments #286, save #289, …); see registry.ts for the `order` values.
import "./calibration.ts";
import "./layout.ts";
import "./segments.ts";
import "./window.ts";
import "./mouse.ts";
import "./bulk-annotations.ts";

export { inspector, type InspectorPanel } from "./registry.ts";
