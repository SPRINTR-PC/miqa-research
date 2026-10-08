// #282 volume views: Crosshairs (three views only, the default there) and V = cycle the 1×1 orientation.
// CS3D side: adapter/cornerstone/volume.ts.
import { commands } from "../commands.ts";
import { cycleOrientation } from "../layout.ts";
import { tools } from "./registry.ts";

export const CROSSHAIRS = "Crosshairs";

tools.register({ id: CROSSHAIRS, label: "Crosshairs", key: "x", group: "nav", icon: "⌖", viewports: ["volume"], minViews: 3 });

commands.register({
  id: "cycle-orientation",
  key: "v",
  label: "Next orientation",
  available: (ctx) => ctx.layout.kind === "volume" && ctx.layout.orientations.length === 1,
  run(ctx) {
    if (ctx.layout.kind !== "volume") return;
    ctx.setLayout({ ...ctx.layout, orientations: [cycleOrientation(ctx.layout.orientations[0])] });
  },
});
