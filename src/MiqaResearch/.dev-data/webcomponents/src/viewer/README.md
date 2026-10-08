# Viewer (`<mires-viewer>`, spec #271)

Lit element in Shadow DOM showing DICOM from our WADO-RS (`/metadata` + `/frames`, session auth).
Cornerstone3D (CS3D, pinned 5.10.11) sits behind an adapter seam, so vitest/happy-dom never loads it.

## Layout

One file per concern, so parallel tickets touch different files.

| Path | What | Owner tickets |
|---|---|---|
| `../mireswc-viewer.ts` | Bundle entry. Re-exports the element only. | — |
| `mires-viewer.ts` | The element: attributes (`can-annotate`), state (`loading`/`ready`/`error`), chrome B layout, keyboard dispatch. Talks to the adapter interface only. | #278, chrome #280 |
| `context.ts` | `ViewerContext`: what inspector panels and commands see (state + actions). | #280, additive |
| `commands.ts` | Keyboard commands registry (I invert, Esc reset built in). | #280, +#282 V, #289 Ctrl/⌘+S |
| `tools/registry.ts` | Tool registry (rail + shortcut keys + role gating). Pure. | #280 |
| `tools/<capability>.ts` | Tool definitions, one module per capability; `tools/stack.ts` = #280's. | #280, #281, #282, #285, #286 |
| `tools/presets.ts` | Window presets (0–8) per modality. Pure. | #280, #284 |
| `tools/bindings.ts` | Workstation mouse as a binding plan of abstract buttons. Pure. | #280, #285 (WSI), #286 (erase) |
| `chrome/*.ts` | Series list, tool rail templates. | #280, #279/#284/#290 (series list) |
| `units.ts` | Tooltip text for CS3D's raw unit suffixes. | #280, #281 |
| `calibration.ts` | Calibration legend per unit, SC spacing shim payload, burned-in badge rule. Pure. | #281 |
| `series.ts` | `/metadata` fetch → ordered `wadors:` frame imageIds. Pure, no CS3D. | #278 |
| `reconstructable.ts` | OHIF reconstructability rule: gates MPR / three views (and fusion). Pure. | #282 |
| `layout.ts` | `ViewLayout` (stack, or volume orientations; slot 0 = big view), V cycle, swap, split (25–85%, localStorage), orientation colours. Pure. | #282 |
| `size-guard.ts` | Size guard: grid estimate from `/metadata`, the 2.5 GiB budget ledger (`SizeGuard`), GPU texture checks, reduced-3D decimation, refusal texts, CS3D cache-error test. Pure. | #283; used by #284, #286 |
| `chrome/size-banner.ts` | Size banner (stack fallback / reduced 3D) and the dismissible refusal message. | #283 |
| `adapter/cornerstone/gpu.ts` | WebGL2 `MAX_3D_TEXTURE_SIZE` / `MAX_TEXTURE_SIZE`. | #283 |
| `chrome/volume-grid.ts` | Volume cells (always three, unused ones hidden) + split divider. | #282 |
| `first-render.ts` | `performance.mark`s, the first-render beacon and the HTTP/1.1 `/frames` warning. Volume views mark `interleaved` / `volume-loaded` on the element's `firstRender`. | #293, volume #282 |
| `adapter/adapter.ts` | **The seam**: `ViewerAdapter` and its view types. Add one member per capability. | all |
| `adapter/stub.ts` | Test double for the seam. Extend it with each new member. | all |
| `adapter/cornerstone/index.ts` | Real adapter: composes the capability modules below. | all (small edits) |
| `adapter/cornerstone/init.ts` | One-time CS3D init, providers. | #278, #282, #285 |
| `adapter/cornerstone/tools.ts` | CS3D tool registry (id → tool class/instance), applies binding plans. | #280; others call `registerCornerstoneTool` from their module |
| `adapter/cornerstone/metadata.ts` | Typed metadata path (`addDicomWebInstance`), never `wadors.metaDataManager`. | #278, spacing shim #281, SUV #284 |
| `adapter/cornerstone/stack.ts` | STACK viewport + its tool group (all registered tools, workstation bindings). | #278, #280, #281 |
| `adapter/cornerstone/volume.ts` | ORTHOGRAPHIC volumes, three views, crosshairs, fusion. | #282–#284 (new) |
| `wsi.ts` | WSI pure parts: `isWholeSlide`, dmv `tilesCacheSize`, geometric-only text lines. | #285 |
| `adapter/cornerstone/wsi.ts` | WHOLE_SLIDE (`MiresWSIViewport` subclass with the dmv tile cache), dmv `peerImport`, head-CSS mirroring. | #285 |
| `bulk-annotations.ts` | Bulk ANN pure parts: find the slide's ANN (object list `?participant=&series=` → `/metadata`, coordinates inline), read its groups. Needs the `participant` attribute. | #292 |
| `adapter/cornerstone/bulk-annotations.ts` | ANN through dmv's annotation-group layer, read-only, show/hide per group (`inspector/bulk-annotations.ts`). | #292 |
| `segmentation.ts` | Segment list (add, rename, colour, active), stack threshold fill, polygon rasterising, threshold defaults. Pure. | #286 |
| `segmentation-controller.ts` | The element's one Segmentation: made on first segment tool (size guard), shown in every view, closed with the element. | #286 |
| `tools/segmentation.ts` | Segment tools (keys g d k q j y m), erase twins, `segmentBindings` (workstation mouse + erase twin on right-drag). | #286 |
| `inspector/segments.ts` | Segments panel: list, brush size, threshold form. | #286 |
| `adapter/cornerstone/segmentation.ts` | Labelmap (derived images per base image; volumes get an image-backed labelmap volume), segment tools, threshold, polygon fill. | #286 |
| `inspector/*.ts` | Side-panel parts, one Lit element or template per panel (calibration legend, layers, segments, save…). | #281, #284, #286, #289+ (new) |
| `*.test.ts` next to the file | vitest, stub adapter, no CS3D. | all |

## Extension points (#280)

Chrome B: series list | tool rail | viewport | inspector. Rail, keys and inspector are built from
registries, so a capability adds entries **from its own files** and touches shared files with one
import line each. Registries throw on duplicate ids/keys, so clashes fail in vitest, not in the UI.

- **A tool** (e.g. Calibrate #281, Crosshairs #282, segment tools #286):
  1. `tools/<capability>.ts`: `tools.register({ id, label, key, group, icon, viewports, annotateOnly })`.
     `id` = CS3D `toolName` (or a tool-instance name), `group` = rail section (`nav`/`measure`/
     `annotate`/`segment`), `viewports` = `stack`/`volume`/`wsi` (spec tool sets),
     `annotateOnly` hides it from view-only roles (rail and key). Add `import "./<capability>.ts"` in `tools/index.ts`.
  2. `adapter/cornerstone/<capability>.ts`: `registerCornerstoneTool(MyTool)` or, for a tool
     instance, `registerCornerstoneTool(Base, { id, configuration })`; `passive: true` keeps
     annotations drawn and editable when the tool is not on a button. Import the module from
     `adapter/cornerstone/index.ts`. Every stack/volume tool group gets all registered tools.
  - `minViews` hides a tool unless that many views are shown (Crosshairs: 3); the element passes `views` in the scope.
  - Keys taken: w p z s l a b o r e f t c (Calibrate, #281) x (Crosshairs, `tools/volume.ts`)
    g d k q j y m (segment tools, `tools/segmentation.ts`); never a tool key: 0–9 (presets), i, v, Esc (`RESERVED_KEYS`).
- **Mouse:** `workstationBindings({ primary, viewport, secondary })` (tools/bindings.ts) is the single
  source of the workstation mouse; views apply it with `applyBindingPlan` (disable-then-activate,
  because CS3D's `setToolActive` merges bindings). WSI (#285): `viewport: "wsi"` (wheel = zoom).
  Segment tools (#286): stack and volume views apply `segmentBindings` (tools/segmentation.ts), which passes
  the tool's erase twin as `secondary` (right-drag erases with the same shape; Eraser and threshold keep W/L).
- **An inspector panel** (e.g. calibration legend #281, layout #282, layers #284, segments #286,
  save #289): `inspector/<panel>.ts` with `inspector.register({ id, order, render(ctx) })`, import it
  in `inspector/index.ts`. `render` gets the `ViewerContext` and returns a Lit template or `nothing`.
  Orders are listed in `inspector/registry.ts`. Shared classes: `section.panel`, `h5`, `.grid2`,
  `.row`, `kbd`, `.hint`; a panel needing its own CSS renders its own custom element.
- **A key command** (V #282, Ctrl/⌘+S #289): `commands.register({ id, key, ctrlOrMeta, label, available, run })`
  from the capability's module.
- **Presets:** `presets.register({ id, label, key, modalities, window | range })` (tools/presets.ts).
- **A view kind** (volume #282, WSI #285): implement `ViewControls` (adapter.ts) so the rail, keys,
  presets and inspector work unchanged; the element's `viewportKind` selects the tool set.
  `ViewerAdapter.close(view)` releases one view (the element closes the stack before opening a volume).
- **Volumes** (#282; fusion #284, size guard #283, segmentation #286 build on it): the series opens as a
  stack; the layout panel (`inspector/layout.ts`) offers 1×1 axial/sagittal/coronal and three views when
  `isReconstructable` passes. `ctx.setLayout(layout)` switches; `openVolume` caches one streaming volume per
  series (`volumeIdFor(seriesUid)` in `adapter/cornerstone/volume.ts`) and reports the first-render stages
  `interleaved` / `volume-loaded`. `interleavedRetrieveStages` is registered for `'volume'` in `init.ts`.
- **Size guard** (#283, `size-guard.ts`): see below.
- **Role:** the page sets the boolean `can-annotate` attribute from the server
  (`ParticipantRights.can_author`: Annotator, PI, Site PI, Admin). It gates Arrow, Calibrate, segment
  tools and Save in the UI only; the server authorises saves again (#287).

## Size guard (#283)

CS3D's 3 GiB cache never evicts the images of a cached volume (or labelmap), so everything open at
once must fit; it throws `CACHE_SIZE_EXCEEDED` / "not cacheable" otherwise. The guard checks first.

- **Estimate:** `seriesGrid(series)` = rows × columns × slices × bytes per voxel (CS3D's data type:
  8-bit 1 B, 16-bit 2 B, float-rescaled 16-bit and PET 4 B, × samples). `labelmapBytes(grid)` = 1 B/voxel.
- **Budget:** 2.5 GiB (`BUDGET_BYTES`), counting `BudgetEntry`s: `volume`, `labelmap`, and one
  `labelmap-reserve` per base series for annotate roles. Per series a labelmap costs
  max(reserve, Σ labelmaps): the first one uses the reserve up, more cost extra.
- **When:** at open (`ctx.volumeFit`) and on every add. The added thing's series (or the series being
  replaced) is removed before counting. A failed check changes nothing; views already open stay.
- **GPU:** `adapter.gpuLimits()` (WebGL2, once). Volumes need every axis ≤ `MAX_3D_TEXTURE_SIZE`;
  a non-WSI 2D image larger than `MAX_TEXTURE_SIZE` is refused at open.
- **Too big for 3D:** the full-resolution stack (default view) with a banner; MPR, crosshairs, fusion off.
  The layout panel offers "Open reduced 3D (view only)": `layout.reduced` = `ijkDecimation` from
  `fitVolume` (in-plane only when rows/columns exceed the 3D texture limit, then the smallest k that fits),
  loaded by `decimatedVolumeLoader`, no labelmap reserve, tool scope `viewOnly` (nav tools + crosshairs).
- **CS3D errors:** `isTooLargeError(e)`; the element shows `TOO_LARGE_MESSAGE` and goes back to the stack
  (open errors, and `VolumeOptions.onTooLarge` for slices refused while streaming).

API for later tickets (`ctx.budget: SizeGuard`, `ctx.refuse(message)`):

```ts
// Fusion overlay (#284): check, then reserve; release when the layer is removed.
const entries = volumeEntries(overlayUid, seriesGrid(overlay)!, false); // overlays get no labelmap reserve
const check = ctx.budget.check(entries);            // replace: ctx.budget.check(entries, [replacedUid])
if (!check.ok) return ctx.refuse(refusalMessage("fusion", check));
ctx.budget.reserve(entries);                         // … ctx.budget.releaseSeries(overlayUid)
// gpu: also refuse when any axis > ctx.gpu.max3dTextureSize (no reduced fusions).

// New labelmap (#286), on the base series' grid:
const r = ctx.budget.reserveLabelmap(baseUid, segmentationId, labelmapBytes(grid));
if (!r.ok) return ctx.refuse(r.message);             // "… Save and close the other Segmentation first."
// … ctx.budget.release(segmentationId) when it's closed; wrap createAndCacheDerived* in isTooLargeError.
```

## Segmentation (#286)

- **One Segmentation per element**, on the base series' grid: `adapter.openSegmentation(series, id)` makes one
  Uint8 labelmap image per base image (`createAndCacheDerivedLabelmapImages`), segmentation id = budget id
  `seg:<seriesUid>`. A stack shows the images; volume views get an image-backed labelmap volume over the
  same images, so painting in either shows in both and the labelmap survives layout switches.
- **Made** on the first segment tool (rail or key) or "New segmentation" in the panel, after
  `ctx.budget.reserveLabelmap`; refused → `ctx.refuse(message)` and the tool stays. CS3D cache errors → "too large".
  Shown in each view after every open / re-layout (`SegmentationView.show`), not in reduced 3D.
- **Tools:** Brush, Eraser (Brush with `ERASE_INSIDE_CIRCLE`), Rectangle/Circle/Sphere scissors (+ `…Erase`
  twins), polygon (linear `SplineROI` instances `PolygonSeg`/`PolygonSegErase`, rasterised on completion; on a
  volume only in axis-aligned planes), Rectangle ROI threshold (passive rectangles, consumed by Run).
- **Threshold:** volumes use CS3D's `rectangleROIThresholdVolumeByRange` on `ctx.thresholdLayer` (the base
  series now; **#284** sets it to the selected layer: its `volumeIdFor(seriesUid)` volume is read). Stacks use
  our own fill (`thresholdPixels`), in modality units.
- **Save (#289):** `ctx.segmentationView`: CS3D segmentation `id` (labelmap image ids via
  `segmentation.state.getSegmentation(id)`), segment labels synced into CS3D's `segments`, colours in
  `state().segments`; `voxelCounts()` tells which segments are non-empty.
- Browser tests read `el.segmentationState` (state + `voxels` per segment).

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
- dicom-microscopy-viewer (WSI) is not bundled: the build copies its `dist/dynamic-import/` (UMD bundle,
  worker, WASM codecs) to `static/js/viewer/dmv/`, and `peerImport` loads it with a classic `<script>`.
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
`viewer_harness_seed` seeds a PI user, a view-only (Investigator) user, their sessions and a synthetic
16-slice CT; tests read them from `browser-tests/fixtures.ts` (`seed()`, `ViewerPage`; log in as the
view-only user with `test.use({ viewOnly: true })`). Add a spec file per feature
(`browser-tests/<feature>.spec.ts`) and extend the seed command for new fixture series.
