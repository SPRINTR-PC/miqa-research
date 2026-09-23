# Packaging Cornerstone3D inside the Lit/Vite web-components build

Research for [#185](https://github.com/SPRINTR-PC/miqa-research/issues/185), map [#176](https://github.com/SPRINTR-PC/miqa-research/issues/176). Date: 2026-09-23.

**Question:** what does it take to ship Cornerstone3D (core, tools, dicom-image-loader, codecs) inside `.dev-data/webcomponents` (Lit 3 + Vite 8 + vitest 5, TS 7) as a web component? Workers, WASM, bundle size, lazy loading, Shadow DOM, licensing, Django static, versions, pitfalls.

Evidence tags: **[doc]** official docs, **[src]** Cornerstone3D source at `cornerstonejs/cornerstone3D@d776002` (2026-09-22), **[npm]** registry metadata, **[spike]** a throwaway build run for this note (Vite 8.3.0, Node 24, CS3D 5.10.10, the repo's `tsconfig.json`), **[inference]** my reading, not verified.

## Answer in brief

- It works with little config. A spike built a Lit element on CS3D 5.10.10 with Vite 8.3.0 and the repo's `tsconfig.json`. `tsc` passed and `vite build` succeeded **without** `@originjs/vite-plugin-commonjs` **[spike]**.
- Add a **third Rollup entry `mireswc-viewer`**. Load it **only on the viewer page**, not in `base.html`, because it is about 1 MB gzipped.
- **Set `base: "./"`, or `base: "/static/js/webcomponents/"`.** This is required: without it, the worker and WASM URLs are emitted as root-absolute `/assets/...`, and Django serves them with a 404 **[spike]**.
- Add `worker: { format: "es" }` and `optimizeDeps.exclude: ["@cornerstonejs/dicom-image-loader"]`, as the docs recommend.
- Shadow DOM: no blocker found in core or tools **[src]**. The known gap is WSI: the microscopy overlay CSS goes into `document.head`. The WSI path also needs `dicom-microscopy-viewer` wired through `peerImport`.
- Licensing: all runtime dependencies are permissive (MIT/BSD/ISC/Apache-2.0/BSL-1.0) **[npm]**.
- vitest/happy-dom can import the modules, but it cannot initialize them (`Worker is not defined`, and there is no WebGL) **[spike]**. Unit tests need a seam; real rendering needs a real browser.

## Versions (npm `latest`, 2026-09-23) [npm]

| Package | Version | License | Unpacked |
|---|---|---|---|
| `@cornerstonejs/core` | 5.10.10 (5.0.0 on 2026-06-09) | MIT | 2.2 MB |
| `@cornerstonejs/tools` | 5.10.10 | MIT | 3.4 MB |
| `@cornerstonejs/dicom-image-loader` | 5.10.10 | MIT | 0.3 MB |
| `@cornerstonejs/metadata`, `@cornerstonejs/utils` | 5.10.10 (new in 5.x, peer deps of core) | MIT | |
| `@kitware/vtk.js` (dep of core, pinned 36.4.1) | 37.2.0 latest | BSD-3-Clause | 13 MB |
| `@cornerstonejs/codec-openjph` / `-charls` / `-openjpeg` | 2.4.x / 1.2.x / 1.3.x | MIT | |
| `@cornerstonejs/codec-libjpeg-turbo-8bit` | 1.2.8 | ISC | |
| `@cornerstonejs/polymorphic-segmentation` (optional, uses `@icr/polyseg-wasm`) | 5.10.10 | MIT | polyseg-wasm 5.7 MB |
| `dicom-microscopy-viewer` (WSI peer) | 0.48.24 | MIT | 39 MB |

Pin all `@cornerstonejs/*` packages to one exact version. They declare exact-version peer dependencies on each other **[npm]**.

5.x changes that matter here:
- Packages are ESM-only (`"type": "module"`, `.js` extensions), and `require()` is unsupported. TS `moduleResolution` must be `bundler`/`node16`/`nodenext`. The repo already uses `bundler` **[doc: migration-guides/5x/1-migration-notes.md "ESM packaging"]**.
- There is a new metadata module: NATURALIZED metadata built from `{ dicomwebJson }` via `metaData.addMetaData`. This is relevant to feeding it from our WADO-RS `/metadata` endpoint **[doc: migration-guides/5x/index.md]**.
- SharedArrayBuffer has not been used since 2.x, so **no COOP/COEP headers are needed** **[doc: migration-guides/2x/1-general.md "Removal of SharedArrayBuffer"]**.

## Web workers and WASM codecs under Vite

- The official Vite setup uses `optimizeDeps.exclude: ['@cornerstonejs/dicom-image-loader']`, `include: ['dicom-parser']`, `worker: { format: 'es' }`, and `viteCommonjs()` for dicom-parser **[doc: getting-started/vue-angular-react-vite.md "Vite › Basic Setup"]**.
- The docs say the codec WASM needs no config under Vite/Rollup. Each decoder does `new URL('@cornerstonejs/codec-…', import.meta.url)`, and Vite resolves and emits it. The `exclude` exists because dev-time prebundling does not resolve these specifiers. A failure shows up as `CompileError: … expected magic word 00 61 73 6d, found 3c 21 64 6f`, which means HTML was served instead of WASM **[doc: same page, "Codec WASM location"]**.
- The loader creates its worker as `new Worker(new URL('./decodeImageFrameWorker.js', import.meta.url), { type: 'module' })`, one per half the cores by default (`maxWebWorkers`) **[src: packages/dicomImageLoader/src/init.ts]**. Tools lazily registers a `computeWorker` the same way, for segmentation stats and similar **[src: packages/tools/src/utilities/registerComputeWorker.ts]**.
- `init({ wasmBasePath })` optionally overrides where all four binaries are loaded from (one root, fixed file names) **[doc: "Codec WASM location"]**.
- **Spike output** (Vite 8.3 with Rolldown, no CommonJS plugin): `mireswc-viewer.js` was 3.55 MB (973 kB gzip). It contained core, tools and vtk.js. `assets/` held `decodeImageFrameWorker-*.js` (135 kB) plus 4 WASM files: openjph 2.30 MB (676 kB gzip), openjpeg 255 kB, libjpeg-turbo 180 kB, charls 145 kB. The worker referenced the hashed WASM names correctly **[spike]**.
- The spike also showed that `viteCommonjs()` is **not needed** on Vite 8, since Rolldown handles `dicom-parser`'s CJS. The official examples predate this: `vite-react-cornerstone3d` still pins CS3D 2.x and Vite 5 **[spike + GitHub cornerstonejs/vite-react-cornerstone3d package.json]**.
- Harmless build noise: "Module fs/path externalized" warnings from the Emscripten codec glue, and "events/url" warnings from vtk.js's xmlbuilder2 **[spike; also reported in cornerstone3D#1802]**.
- `worker.rollupOptions` is deprecated in Vite 8; use `worker.rolldownOptions` **[doc: vite.dev/config/worker-options]**. The CS3D docs' `external: ['@icr/polyseg-wasm']` hint therefore goes under `rolldownOptions` if PolySeg is added.
- For PolySeg or labelmap interpolation, also add `assetsInclude: ['**/*.wasm']` and those packages to `optimizeDeps.exclude` **[doc: "Advanced Setup"]**.

## Asset base path: the main pitfall for Django static

With the repo's current config (no `base`), the spike emitted `new URL("/assets/decodeImageFrameWorker-….js", import.meta.url)`. That resolves to `https://host/assets/…`, not `/static/js/webcomponents/assets/…`, so it returns 404 **[spike]**. With `base: "./"` the output becomes `new URL("assets/…", import.meta.url)`, which is relative to the module **[spike]**. Vite: "you may set a relative base path with `base: './'` … all generated URLs [become] relative to each file" **[doc: vite.dev/guide/build "Relative base"]**.

The existing chart entries are unaffected: ES `import` chunk paths are already relative. Setting `base` only changes `new URL(…, import.meta.url)` and CSS `url()` **[inference]**.

## Bundle size and lazy loading

- Recommend a separate entry, `src/mireswc-viewer.ts`, added to `build.rollupOptions.input` next to `mireswc` and `mireswc-charts`. Lit is then shared through `chunks/` **[inference, based on the existing config]**.
- `templates/base.html` loads `mireswc.js` and `mireswc-charts.js` on **every page**. The viewer bundle must **not** be added there. Load it from the viewer page template only, which the sibling map opens in a new tab.
- Within the entry, lazily `import()` the optional heavy parts: PolySeg WASM, and `dicom-microscopy-viewer` for WSI only. The codecs are already loaded on demand inside the worker (`jpeg`/`lossless` split into their own chunks) **[spike]**.
- Build output is committed under `static/js/webcomponents/`. Each rebuild adds about 6.5 MB of hashed files to git history. Consider gitignoring the output and building in CI/Docker instead **[inference]**.

## Shadow DOM compatibility

The official docs neither claim nor deny Shadow DOM support. GitHub issue searches for "shadow dom", "shadowRoot" and "web component" returned no relevant issues **[gh search, 2026-09-23]**. From the source:

- Rendering is element-scoped. `enableElement({ element })` takes any `HTMLDivElement` and sets `element.tabIndex = -1` **[src: core/src/RenderingEngine/BaseRenderingEngine.ts:575]**. The SVG annotation layer is found with `element.querySelector(...)` **[src: tools/src/drawingSvg/getSvgDrawingHelper.ts:40]**. Both work on a node inside a shadow root.
- Mouse drag attaches `mousemove`/`mouseup` to `document`, but uses the stored `state.element` and coordinates, not `evt.target` **[src: tools/src/eventListeners/mouse/mouseDownListener.ts:198]**. This is fine under event retargeting. `keydown` is attached to the element, so the viewport div must be focusable/focused **[src: keyboard/index.ts]**.
- No `document.querySelector`, `elementFromPoint` or `getRootNode` lookups on the rendering path. The only `document.*` DOM lookups are in doc comments, the stats overlay, `renderToCanvasGPU`, and WSI **[src grep]**.
- **Gap (WSI):** `addWSIMiniNavigationOverlayCss()` appends a `<style>` to `document.head` **[src: core/src/utilities/WSIUtilities.ts:131]**. That CSS will not reach inside a shadow root. Mirror it into the component's `static styles`, or render the WSI viewport in light DOM. OpenLayers' own CSS (used by dicom-microscopy-viewer) has the same issue **[inference]**.
- Cornerstone does not observe resizes. The component should use a `ResizeObserver` and call `renderingEngine.resize()` **[inference]**.
- Not yet verified in a real browser. The first `prototype` should smoke-test pan/zoom/length/crosshairs inside a shadow root.

**Fallback if Shadow DOM breaks:** override `createRenderRoot() { return this; }` so the Lit element renders in light DOM **[inference]**.

## WSI (pathology)

Both the legacy `WSIViewport` and the 5.x `WSIGenericViewport` render through `dicom-microscopy-viewer`, obtained via `init({ peerImport })` **[src: core/src/RenderingEngine/WSIViewport.ts:38-47; GenericViewport/WSI/DicomMicroscopyRenderPath.ts]**. The demo loads its prebuilt UMD `dicomMicroscopyViewer.min.js` as a global **[src: utils/demo/helpers/initDemo.ts:88]**.

That package ships webpack bundles (2.6 MB main, or 9.2 MB for the dynamic-import build) with its own worker and its own copies of the codec WASM **[npm/jsdelivr file listing]**. Plan to serve it as a separate static asset that is lazily loaded only for WSI series. This is a separate ticket-sized concern.

## vitest / happy-dom

The spike imported CS3D and defined the Lit element under happy-dom. Initialization then failed with `ReferenceError: Worker is not defined` in `dicomImageLoader init`, and there is no WebGL either **[spike]**. Recommendation:
- Put Cornerstone behind a small adapter seam, then unit-test the Lit element and the WADO-RS/metadata mapping with the adapter stubbed.
- Cover rendering with a real browser: Vitest browser mode or Playwright against `vite preview` or the Django page.

## Licensing [npm, spike dependency-tree scan]

All runtime licenses are permissive:
- **MIT:** CS3D packages, dicom-parser, dcmjs, dicom-microscopy-viewer
- **BSD-3-Clause:** vtk.js, Lit
- **ISC:** libjpeg-turbo codec, d3-*
- **Apache-2.0:** comlink
- **BSL-1.0:** clipper2-ts, used by tools
- **MIT AND Zlib:** pako

The WASM codecs wrap BSD-licensed C/C++ libraries (OpenJPEG, CharLS, OpenJPH) plus libjpeg-turbo (IJG/BSD) **[inference, not checked per file]**. No copyleft. Keep the license banners and attribute Apache-2.0 NOTICE if distributing.

## Serving via Django static

- Files land in `STATICFILES_DIRS = [BASE_DIR / "static"]` through `outDir: ../../static/js/webcomponents` **[repo: settings.py:497-503, vite.config.ts]**.
- In DEBUG they are served by `ASGIStaticFilesHandler` **[repo: MiqaResearch/asgi.py]**. Python 3.14 `mimetypes` maps `.wasm` to `application/wasm`, which `WebAssembly.instantiateStreaming` requires **[spike]**. The Emscripten glue also falls back to ArrayBuffer instantiation on a wrong MIME type **[src: codec-openjph/dist/openjphjs.js]**.
- In production, whatever serves `STATIC_ROOT` must send `application/wasm` for `.wasm` (verify for the actual server/proxy).
- The current default `StaticFilesStorage` is fine. If `ManifestStaticFilesStorage` is ever enabled, Vite already content-hashes these files, and Django's post-processing does not rewrite `new URL(…, import.meta.url)` strings **[inference]**.
- There is no CSP today. If one is added, it needs `script-src 'self' 'wasm-unsafe-eval'` and `worker-src 'self'` **[inference from CSP spec]**.
- Workers must be same-origin as the page. A CDN for static files would need `wasmBasePath` and a same-origin worker **[inference]**.

## Suggested `vite.config.ts` delta

```ts
export default defineConfig({
  base: "./",                                   // worker/WASM URLs relative to the module
  optimizeDeps: {
    exclude: ["@cornerstonejs/dicom-image-loader"],
    include: ["dicom-parser"],
  },
  worker: { format: "es" },
  build: {
    rollupOptions: {
      input: {
        "mireswc": resolve(__dirname, "src/mireswc.ts"),
        "mireswc-charts": resolve(__dirname, "src/mireswc-charts.ts"),
        "mireswc-viewer": resolve(__dirname, "src/mireswc-viewer.ts"),
      },
      // output unchanged
    },
  },
});
```

## Known pitfalls (collected)

1. Root-absolute asset URLs without `base` cause the worker/WASM to 404 under `/static/` **[spike]**.
2. Prebundling `dicom-image-loader` in `vite dev` produces the `<!do` WASM error **[doc]**.
3. Tool names get mangled by minification, e.g. `LengthTool` registered as `"FE"`. The docs' workaround is `minify: false`. Prefer referencing `Tool.toolName` rather than class names **[doc: Troubleshooting §3]**.
4. `No known conditions for "./types"` build error: alias `@cornerstonejs/core` to `dist/esm` **[doc: Troubleshooting §2]**. It did not occur in the spike.
5. `loadAndCacheImage` has a reported 8x slowdown after a Vite build. The issue is open and unresolved **[cornerstone3D#1802]**.
6. Mismatched `@cornerstonejs/*` versions: the peer dependencies are exact **[npm]**.
7. WSI CSS injected into `document.head` does not reach a shadow root **[src]**.
8. The official Vite example repos are stale (CS3D 2.x, Vite 5). Do not copy their dependency lists **[GitHub]**.

## Sources

- Cornerstone3D docs source: `packages/docs/docs/getting-started/vue-angular-react-vite.md`, `installation.md`, `migration-guides/5x/*`, `migration-guides/2x/1-general.md`, at https://github.com/cornerstonejs/cornerstone3D (commit d7760029, 2026-09-22); rendered at https://www.cornerstonejs.org/docs/getting-started/vue-angular-react-etc
- Cornerstone3D source files cited inline (same commit)
- npm registry: `https://registry.npmjs.org/<pkg>/latest`
- Vite docs: https://vite.dev/guide/build.html (Relative base), https://vite.dev/config/worker-options.html
- https://github.com/cornerstonejs/vite-react-cornerstone3d (vite.config.ts, package.json)
- Issues: cornerstonejs/cornerstone3D#1802, #1876, #2286
- Spike: throwaway project in the session scratchpad (Lit element + CS3D 5.10.10 + Vite 8.3.0), not committed
