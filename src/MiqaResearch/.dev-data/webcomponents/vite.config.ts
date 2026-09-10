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
    setupFiles: ["./src/vitest-setup.ts"],
  },
});
