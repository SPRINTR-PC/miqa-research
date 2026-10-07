/// <reference types="vitest" />
import { resolve } from "node:path";
import { defineConfig } from "vitest/config";

export default defineConfig({
  publicDir: false,
  define: {
    global: "globalThis",
  },
  resolve: {
    alias: [
      {
        find: "buffer/",
        replacement: "buffer",
      },
      {
        // Anchored regex, not a plain string: a string `find` here matches
        // as a prefix (rewriting "plotly.js/lib/core" too, which is exactly
        // what plotly-custom.ts itself imports — an infinite alias loop).
        // See that file for why the full "plotly.js" package is never
        // imported directly.
        find: /^plotly\.js$/,
        replacement: resolve(__dirname, "src/charts/plotly-custom.ts"),
      },
    ],
  },
  build: {
    outDir: "../../static/js/webcomponents",
    emptyOutDir: true,
    rollupOptions: {
      input: {
        "mireswc": resolve(__dirname, "src/mireswc.ts"),
        "mireswc-charts": resolve(__dirname, "src/mireswc-charts.ts"),
      },
      output: {
        entryFileNames: "[name].js",
        chunkFileNames: "chunks/[name]-[hash].js",
        assetFileNames: "assets/[name]-[hash][extname]",
      },
      external: ["buffer/"],
    },
  },
  test: {
    environment: "happy-dom",
    // Unit tests only; Playwright browser tests (browser-tests/) run via `npm run test:browser`.
    include: ["src/**/*.test.ts"],
    setupFiles: ["./src/vitest-setup.ts"],
  },
});
