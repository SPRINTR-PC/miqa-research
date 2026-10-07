# Viewer (`<mires-viewer>`, spec #271)

Lit element in Shadow DOM showing DICOM from our WADO-RS (`/metadata` + `/frames`, session auth).
Cornerstone3D (CS3D, pinned 5.10.11) sits behind an adapter seam, so vitest/happy-dom never loads it.

## Layout

One file per concern, so parallel tickets touch different files.

| Path | What | Owner tickets |
|---|---|---|
| `../mireswc-viewer.ts` | Bundle entry. Re-exports the element only. | — |
| `mires-viewer.ts` | The element: attributes, state (`loading`/`ready`/`error`), layout. Talks to the adapter interface only. | #278, chrome #280 |
| `series.ts` | `/metadata` fetch → ordered `wadors:` frame imageIds. Pure, no CS3D. | #278 |
| `first-render.ts` | `performance.mark`s, the first-render beacon and the HTTP/1.1 `/frames` warning. Volume views mark `interleaved` / `volume-loaded` on the element's `firstRender`. | #293, volume #282 |
| `adapter/adapter.ts` | **The seam**: `ViewerAdapter` and its view types. Add one member per capability. | all |
| `adapter/stub.ts` | Test double for the seam. Extend it with each new member. | all |
| `adapter/cornerstone/index.ts` | Real adapter: composes the capability modules below. | all (small edits) |
| `adapter/cornerstone/init.ts` | One-time CS3D init, providers, global tool registration. | #278, #282, #285, #286 |
| `adapter/cornerstone/metadata.ts` | Typed metadata path (`addDicomWebInstance`), never `wadors.metaDataManager`. | #278, spacing shim #281, SUV #284 |
| `adapter/cornerstone/stack.ts` | STACK viewport + its tool group. | #278, #280, #281 |
| `adapter/cornerstone/volume.ts` | ORTHOGRAPHIC volumes, three views, crosshairs, fusion. | #282–#284 (new) |
| `adapter/cornerstone/wsi.ts` | WHOLE_SLIDE (`WSIViewport` subclass), dmv `peerImport`. | #285 (new) |
| `adapter/cornerstone/segmentation.ts` | Labelmaps, segment tools, threshold. | #286 (new) |
| `inspector/*.ts` | Side-panel parts, one Lit element or template per panel (calibration legend, layers, segments, save…). | #281, #284, #286, #289+ (new) |
| `*.test.ts` next to the file | vitest, stub adapter, no CS3D. | all |

Rules:
- Only `adapter/cornerstone/**` imports `@cornerstonejs/*`. The element loads it with a dynamic `import()`.
- Reference CS3D tools by `Tool.toolName`: minify mangles class names.
- Browser behaviour (rendering, mouse, WASM) is tested in `../../browser-tests/` (Playwright), not vitest.

## Build and output

- `npm run build:viewer` builds with `vite.viewer.config.ts` into `src/MiqaResearch/static/js/viewer/`.
  It's a separate build from `npm run build` (core + charts), so it never rewrites the committed
  `static/js/webcomponents/` bundles.
- `static/js/viewer/` is **gitignored, never committed**: the prod `Dockerfile` builds it in its `viewer`
  stage. Locally, run `npm run build:viewer` before opening the viewer.
- Only the viewer page loads `{% static 'js/viewer/mireswc-viewer.js' %}`; `base.html` never does.
- The static server must serve `.wasm` as `application/wasm` (Django's static view does; checked by
  the browser tests). No CSP today; one would need `'wasm-unsafe-eval'` and `worker-src 'self'`.
  Both are in the technical manual's deployment requirements (`documentation/manuals/technical/src/deployment.md`).
- The host page must set the `csrftoken` cookie (`ensure_csrf_cookie`, or any `{% csrf_token %}`):
  the viewer's POSTs send it as `X-CSRFToken`.

## Dev page

`/viewer/dev/?study=<StudyInstanceUID>&series=<SeriesInstanceUID>` (pseudonymized UIDs, as in `/metadata`).
Login required, 404 unless DEBUG. Temporary until the viewer page of #279.

## Browser tests (local only, not in CI)

```sh
npm ci
npx playwright install chromium   # once
npm run test:browser              # builds the viewer, then runs browser-tests/
```

Headless Chromium with SwiftShader WebGL against Django `runserver` on port 8278, using
`MiqaResearch.settings_viewer_harness` (DEBUG, demo encryption keys) and **its own database**
(`<your dev db>_viewer_harness`, created and migrated automatically; override with
`VIEWER_HARNESS_DATABASE_URL`). Needs `src/MiqaResearch/.env`, Postgres and `uv`.
`viewer_harness_seed` seeds a PI user, a session and a synthetic 16-slice CT; tests read them from
`browser-tests/fixtures.ts` (`seed()`, `ViewerPage`). Add a spec file per feature
(`browser-tests/<feature>.spec.ts`) and extend the seed command for new fixture series.
