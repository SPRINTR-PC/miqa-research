// #281 Calibrate (User spacing calibration): stack only, annotate roles only (spec tool sets).
// CS3D side: adapter/cornerstone/calibration.ts.
import { tools } from "./registry.ts";

tools.register({
  id: "Calibrate",
  label: "Calibrate (known length)",
  key: "c",
  group: "measure",
  icon: "⇹",
  viewports: ["stack"],
  annotateOnly: true,
});
