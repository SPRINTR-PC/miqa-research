// Viewer bundle (spec #271): a build of its own so CS3D's workers/WASM/chunks never mix
// with the core/charts bundles, and its emptyOutDir only ever wipes static/js/viewer/.
// That directory is gitignored and built at deploy (Dockerfile `viewer` stage).
import { resolve } from "node:path";
import { defineConfig } from "vite";

export default defineConfig({
  // Relative base: worker and WASM URLs resolve next to the bundle under /static/ (else 404).
  base: "./",
  publicDir: false,
  worker: { format: "es" },
  optimizeDeps: { exclude: ["@cornerstonejs/dicom-image-loader"] },
  build: {
    outDir: "../../static/js/viewer",
    emptyOutDir: true,
    // CS3D core is ~3.5 MB minified (~1 MB gzip) by design; see research #185.
    chunkSizeWarningLimit: 4000,
    rollupOptions: {
      input: { "mireswc-viewer": resolve(import.meta.dirname, "src/mireswc-viewer.ts") },
      output: {
        entryFileNames: "[name].js",
        chunkFileNames: "chunks/[name]-[hash].js",
        assetFileNames: "assets/[name]-[hash][extname]",
      },
    },
  },
});
