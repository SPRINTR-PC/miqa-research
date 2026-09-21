// plotly.js ships types only for its package root (`plotly.js/lib/index.d.ts`);
// these deep `lib/*` entry points used by plotly-custom.ts to build a
// trimmed-down bundle have no declaration files of their own.
declare module "plotly.js/lib/core";
declare module "plotly.js/lib/bar";
declare module "plotly.js/lib/box";
declare module "plotly.js/lib/heatmap";
declare module "plotly.js/lib/histogram";
declare module "plotly.js/lib/histogram2d";
declare module "plotly.js/lib/histogram2dcontour";
declare module "plotly.js/lib/pie";
declare module "plotly.js/lib/sankey";
declare module "plotly.js/lib/scattergl";
