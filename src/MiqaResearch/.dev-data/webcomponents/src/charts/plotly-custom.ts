import Plotly from "plotly.js/lib/core";
import bar from "plotly.js/lib/bar";
import box from "plotly.js/lib/box";
import heatmap from "plotly.js/lib/heatmap";
import histogram from "plotly.js/lib/histogram";
import histogram2d from "plotly.js/lib/histogram2d";
import histogram2dcontour from "plotly.js/lib/histogram2dcontour";
import pie from "plotly.js/lib/pie";
import sankey from "plotly.js/lib/sankey";
import scattergl from "plotly.js/lib/scattergl";

/**
 * Aliased in place of the full "plotly.js" package (see vite.config.ts) for
 * every runtime import. The full package registers every trace type,
 * including "image", whose helpers pull in `probe-image-size` /
 * `stream-parser` — packages that reach for Node's `stream`/`assert` core
 * modules at import time (not lazily), which Vite externalizes to empty
 * shims in the browser and crashes on (`Transform.prototype` of undefined).
 * No chart element here ever renders an "image" trace, so this registers
 * only the trace types the chart components actually use (`scatter` is
 * already registered by `lib/core` itself) instead of pulling that in.
 */
Plotly.register([bar, box, heatmap, histogram, histogram2d, histogram2dcontour, pie, sankey, scattergl]);

export default Plotly;
