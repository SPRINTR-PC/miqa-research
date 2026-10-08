// Viewer bundle (spec #271): a build of its own so CS3D's workers/WASM/chunks never mix
// with the core/charts bundles, and its emptyOutDir only ever wipes static/js/viewer/.
// That directory is gitignored and built at deploy (Dockerfile `viewer` stage).
import { copyFileSync, mkdirSync, readdirSync } from "node:fs";
import { resolve } from "node:path";
import { defineConfig, type Plugin } from "vite";

const OUT_DIR = resolve(import.meta.dirname, "../../static/js/viewer");

// dicom-microscopy-viewer (WSI, #285) is served as-is from <outDir>/dmv/: its UMD bundle, data-loader
// worker and WASM codecs (dist/dynamic-import/, no source maps). peerImport loads it with a classic
// <script> (adapter/cornerstone/wsi.ts). Copied after the bundle is written, since emptyOutDir wipes outDir.
function dicomMicroscopyViewerAssets(): Plugin {
  const from = resolve(import.meta.dirname, "node_modules/dicom-microscopy-viewer/dist/dynamic-import");
  return {
    name: "dicom-microscopy-viewer-assets",
    apply: "build",
    writeBundle() {
      const to = resolve(OUT_DIR, "dmv");
      mkdirSync(to, { recursive: true });
      for (const file of readdirSync(from).filter((f) => /\.(js|wasm)$/.test(f))) {
        copyFileSync(resolve(from, file), resolve(to, file));
      }
    },
  };
}

export default defineConfig({
  // Relative base: worker and WASM URLs resolve next to the bundle under /static/ (else 404).
  base: "./",
  publicDir: false,
  worker: { format: "es" },
  optimizeDeps: { exclude: ["@cornerstonejs/dicom-image-loader"] },
  plugins: [dicomMicroscopyViewerAssets()],
  build: {
    outDir: OUT_DIR,
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
