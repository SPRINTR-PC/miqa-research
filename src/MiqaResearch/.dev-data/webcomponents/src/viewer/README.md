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
| `chrome/*.ts` | Series list (with the page's `SeriesEntry`), tool rail templates. | #280, #279/#284/#290 (series list) |
| `units.ts` | Tooltip text for CS3D's raw unit suffixes. | #280, #281 |
| `calibration.ts` | Calibration legend per unit, SC spacing shim payload, burned-in badge rule. Pure. | #281 |
| `series.ts` | `/metadata` fetch → ordered `wadors:` frame imageIds. Pure, no CS3D. | #278 |
| `reconstructable.ts` | OHIF reconstructability rule: gates MPR / three views (and fusion). Pure. | #282 |
| `layout.ts` | `ViewLayout` (stack, or volume orientations; slot 0 = big view), V cycle, swap, split (25–85%, localStorage), orientation colours. Pure. | #282 |
| `size-guard.ts` | Size guard: grid estimate from `/metadata`, the 2.5 GiB budget ledger (`SizeGuard`), GPU texture checks, reduced-3D decimation, refusal texts, CS3D cache-error test. Pure. | #283; used by #284, #286 |
| `fusion.ts` | Fusion rules: fuse / replace blockers (Frame of Reference, volumes only), overlay budget, layer display defaults (PET curve), curated colormaps, overlay drag W/L, curve edits. Pure. | #284 |
| `suv.ts` | SUV inputs from `/metadata` for calculate-suv, `SuvStatus` and the Bq/ml warning. Pure. | #284 |
| `chrome/drop-zones.ts` | Drop zones over the big view while a series is dragged: top = fuse, bottom = replace. | #284 |
| `test-fixtures.ts` | DICOM JSON fixtures for unit tests (PET with SUV inputs, volume series). | #284, all |
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
| `adapter/cornerstone/volume.ts` | ORTHOGRAPHIC volumes, three views, crosshairs, fusion layers. | #282–#284 |
| `adapter/cornerstone/fusion.ts` | `LayerWindowLevel` tool (right-drag W/L of the selected overlay), layer colormap properties. | #284 |
| `adapter/cornerstone/suv.ts` | Whole-series SUVbw `scalingModule` (calculate-suv) and the applied/not status per series. | #284 |
| `wsi.ts` | WSI pure parts: `isWholeSlide`, dmv `tilesCacheSize`, geometric-only text lines. | #285 |
| `adapter/cornerstone/wsi.ts` | WHOLE_SLIDE (`MiresWSIViewport` subclass with the dmv tile cache), dmv `peerImport`, head-CSS mirroring. | #285 |
| `bulk-annotations.ts` | Bulk ANN pure parts: find the slide's ANN (object list `?participant=&series=` → `/metadata`, coordinates inline), read its groups. Needs the `participant` attribute. | #292 |
| `adapter/cornerstone/bulk-annotations.ts` | ANN through dmv's annotation-group layer, read-only, show/hide per group (`inspector/bulk-annotations.ts`). | #292 |
| `segmentation.ts` | Segment list (add, rename, colour, active), stack threshold fill, polygon rasterising, threshold defaults. Pure. | #286 |
| `segmentation-controller.ts` | The element's one Segmentation: made on first segment tool (size guard), shown in every view, closed with the element. | #286 |
| `tools/segmentation.ts` | Segment tools (keys g d k q j y m), erase twins, `segmentBindings` (workstation mouse + erase twin on right-drag). | #286 |
| `inspector/segments.ts` | Segments panel: list, brush size, threshold form. | #286 |
| `adapter/cornerstone/segmentation.ts` | Labelmap (derived images per base image; volumes get an image-backed labelmap volume), segment tools, threshold, polygon fill. | #286 |
| `save.ts` | `SaveController`: Save per kind (edits = revisions past the last save/load), "Supersede vN → vN+1" / "Save as new (v1)", POST `/objects`, the 409 conflict and its three outcomes. No CS3D. | #289 |
| `sr.ts` | SR TID 1500 post-processing (true UCUM units, calibration qualifier, User reference line) and reading User calibrations back; the adapter's 12 exportable tools. Pure. | #289 |
| `simplify.ts` | Douglas–Peucker for WSI freehand contours. Pure. | #289 |
| `inspector/save.ts`, `chrome/save-dialogs.ts` | Save buttons (+ Ctrl/⌘+S, dropped-tool warning); toast and 409 dialog over the view. | #289 |
| `results.ts` | `ResultsController`: the results tree's state (chains from `GET /objects`, blinding status, shown heads, menu / History / confirm) and actions (show / hide via the element, Retire, Blinding Reveal, Show retired). No CS3D. | #290 |
| `viewer-session.ts` | Per-open Viewer Session id (the page's `viewer-session`, else made here), sent as `X-Mires-Viewer-Session` on every viewer request; the server scopes a Blinding Reveal to it (ends on reload / other tabs). | #288, #279 |
| `chrome/results-tree.ts` | Result rows under each series (⊕ Fusion badge, ⋯ History / Retire), lock row, "Show retired" footer, chips over the viewport, the Retire / Reveal confirm. | #290 |
| `saved-seg.ts` | A saved SEG for showing: `/metadata` + all frames in one `/frames` request (multipart/related parser). | #290 |
| `adapter/cornerstone/annotations.ts` | `AnnotationSet`: edit counting, SR export with `@cornerstonejs/adapters` (WSI: SCOORD3D, simplified, geometric only), SR import + User calibration reapply. | #289 |
| `drafts.ts`, `chrome/draft-banner.ts` | Drafts: IndexedDB autosave (per user × participant × series × kind, 7-day TTL) and the Restore / Discard banner. No CS3D. | #291 |
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
  Volume right-drag precedence: erase twin > `LayerWindowLevel` on a selected overlay (#284) > W/L.
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
- **Fusion** (#284): see below.
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
- **Threshold:** volumes use CS3D's `rectangleROIThresholdVolumeByRange` on `ctx.thresholdLayer` (the
  selected layer (#284), else the base series: its `volumeIdFor(seriesUid)` volume is read; the form's default
  range follows its modality). Stacks use
  our own fill (`thresholdPixels`), in modality units.
- **Save (#289):** `ctx.segmentationView`: CS3D segmentation `id` (labelmap image ids via
  `segmentation.state.getSegmentation(id)`), segment labels synced into CS3D's `segments`, colours in
  `state().segments`; `voxelCounts()` tells which segments are non-empty.
- Browser tests read `el.segmentationState` (state + `voxels` per segment).

## Save (#289)

- **Buttons:** `inspector/save.ts` (order 10), one per kind, annotate roles only; Ctrl/⌘+S saves both. Enabled when the
  kind's revision moved past the last save/load and there is something to save (never an empty SR/SEG: retire instead, #290).
  Label: "Supersede vN → vN+1" on top of a head the user may change (`can_change`), else "Save as new (v1)".
  A toast confirms; the 409 dialog (`chrome/save-dialogs.ts`) names author, version and time and offers
  "Discard mine, load theirs", "Save mine as a separate object", "Save mine on top" (only with `can_change` from the 409 body).
- **Edits:** `adapter.watchAnnotations(onChange)` (`AnnotationSet.revision()`: annotation completed/changed/removed,
  not `StatsUpdated`, and every User calibration) and `SegmentationController.revision()` (painting, threshold,
  polygon, segment add/rename/colour; closing bumps it).
- **SR:** CS3D's `MeasurementReport.generateReport` (one measurement group per annotation, in toolState order),
  then `sr.ts`: units rewritten from CS3D's raw unit (`mm`, `cm`, `{pixels}`, `{square pixels}`; dcmjs labels every Length `mm`),
  qualifier `(SpacingCalib, 99MIRES)` = CS3D's unit suffix (`Proj`, `User`, …; `Uncalibrated` for px; none for plain mm),
  and for `User` a nested `(UserCalibration, 99MIRES)` container: NUM `(CalKnownLength)` in mm inferred from a SCOORD POLYLINE
  (reference line, image coordinates) on its IMAGE. Nested because the adapter reads a group's first NUM as its measurement.
  SOP class Comprehensive 3D SR. Only the adapter's 12 tools are exported; the panel warns about others.
- **WSI:** annotations go through the adapter's 3D path (`SlideReport`: the slide's base level as referenced image) → SCOORD3D
  in slide mm with the Frame of Reference; only geometric stats; PlanarFreehandROI contours simplified (`simplify.ts`) at 1 screen
  pixel in mm measured when the contour was completed.
- **SEG:** `SegmentationView.exportSeg()`: `generateSegmentation` (66.4 BINARY) over the cached base images and their labelmaps,
  segment label + colour (CIELab), algorithm MANUAL, coded as Tissue.
- **Reopen:** `AnnotationSet.importSr(instance, series)` takes the SR's `/metadata` DICOM JSON (sessions can't fetch raw bytes),
  reapplies its User calibrations (`applyUserCalibration`), then adds the annotations (returns their ids for `remove`).
  Used by "load theirs" and the results tree (#290). "Load theirs" on a SEG shows their SEG (below).

## Results tree (#290)

- **Listing:** `GET /objects?participant=` (+ `include_retired=true` with "Show retired") and `GET /participants/{id}/blinding`
  once the element is ready; nothing without the `participant` attribute. Rows nest under the series row of their
  `base_series_uid` (the first source series sent on save = the Fusion base; ingested objects: their first source),
  with "⊕ PT" naming the other sources. Chains whose base isn't in the series list aren't shown.
- **Show:** the base series replaces the shown one if needed (`replace`, size guard), other sources are fused (`fuse`),
  then SR → `importSr` (ids kept per chain) or SEG → `SegmentationController.load` (see below). The head becomes
  Save's head (`save.setHead`). One Segmentation at a time: another SEG replaces the shown one; unsaved Segmentation
  edits refuse the load. Replacing the base series (drag or tree) hides heads of the old one.
- **Hide** (row click again, chip ✕): `AnnotationSet.remove(ids)` / `segmentation.close()`; Save forgets that head
  (`save.forgetHead`) or moves to another shown head of the kind.
- **SEG load:** `saved-seg.ts` fetches `/metadata` + `/frames/1,…,n` (sessions get 403 on raw bytes); `openSegmentation(…, saved)`
  runs `createLabelmapsFromSegImageIds` with the served header as `multiframe` and our frames as `decodeImageData`
  (it unpacks BINARY), copies its labelmaps into ours and drops them; segment labels and colours (CIELab → RGB) from
  `SegmentSequence`. Planar SEGs only (CS3D refuses others).
- **Retire / Reveal:** ⋯ → Retire… (only `can_change`, annotate roles) → confirm → `POST /objects/{id}/retire`, list refreshed.
  Lock row on Blinded Annotation: "N hidden"; `can_reveal` → confirm → `POST /participants/{id}/blinding-reveal`.
  "Show retired" footer for annotate roles; retired rows are read-only. View-only: rows show/hide and History only.
- Browser tests: `browser-tests/results.spec.ts`; the seed's `blinded` participant (project "Viewer harness blinded",
  one ingested SR hidden from the PI).

## Drafts (#291)

- `drafts.ts`: `DraftStore` (IndexedDB `mires-viewer-drafts`, key per user × participant × series × kind, 7-day TTL,
  expired ones purged on open) and `DraftController` (autosave 500 ms after an edit while Save is dirty; `saved(kind)`
  clears it, from `SaveHost.saved` on 201 and on "load theirs"). No user (`user` attribute, the page sets the pk),
  no participant or view-only: no drafts. Survive logout (`Clear-Site-Data: "cache"` only).
- Data = Cornerstone JSON from the adapter: `AnnotationSet.snapshot/restore` (CS3D annotations without cachedStats,
  plus User calibrations), `SegmentationView.snapshot/restore` (segments + per-image labelmap runs, `encodeRuns`).
  The draft keeps its base head (`SaveController.base`); Restore sets it as head first, so Save offers "Supersede vN → vN+1".
- `chrome/draft-banner.ts`: banner over the view on open (and after replace) with Restore / Discard per kind. While a
  kind's draft is offered it isn't autosaved, so new edits never overwrite it unseen.
- **#290:** loading a head through the tree should go through `ctx.save.setHead` as before; a loaded head with an
  offered draft for the same series is fine (Restore replaces what is shown).

Rules:
- Only `adapter/cornerstone/**` imports `@cornerstonejs/*`. The element loads it with a dynamic `import()`.
- Reference CS3D tools by `Tool.toolName`: minify mangles class names.
- Browser behaviour (rendering, mouse, WASM) is tested in `../../browser-tests/` (Playwright), not vitest.

## Fusion (#284)

- **Series list:** the page's series list (see Entry contract) gives the rows; a Related Series'
  `/metadata` loads only when it is dropped onto the view, from its own study.
  Rows are draggable; while dragging, the big view shows two drop zones (`chrome/drop-zones.ts`).
- **Top half = fuse** into every view: `fuseBlocker` (same `FrameOfReferenceUID`, both reconstructable,
  not shown yet, not reduced 3D, base fits full-resolution 3D) then `overlayBudget` (texture limit + budget,
  no labelmap reserve). From the stack the base opens in three views first (both checked before anything
  opens). Refusals show the reason (`ctx.refuse`). The new overlay is selected.
- **Bottom half = replace:** views closed, shown series evicted from CS3D's cache (`adapter.evict`) and
  released from the budget, the series opened as a stack/slide, then in the previous volume layout if it
  fits. Closing a volume view does **not** free overlays: CS3D keeps their volumes cached.
- **Layers** (`VolumeState.layers`, base first; `inspector/layers.ts`): select (right-drag W/L via
  `LayerWindowLevel`, `setVoi`/presets and `ctx.modality` follow the selected layer), remove, colormap
  (curated vtk.js presets; CS3D resolves names its empty registry lacks against vtk.js), opacity
  multiplier and curve (`opacityMapping`, data units). PET overlay default in SUV: hsv, SUV 0–5,
  0 % up to SUV 2, 100 % from SUV 4; in Bq/ml: flat 50 %. Reduced 3D shows the panel for the base colormap.
- **SUV:** `registerSeriesMetadata` adds whole-series SUVbw factors for PT; the status is what CS3D
  will use (`scalingModule.suvbw` present). PatientSex other than M/F is left out (calculate-suv throws).
  Not applied → a `.suv-warning` badge ("Bq/ml, not SUV …") in the layers panel or, on the stack, "Units".
- **CS3D gotchas:** `addVolumesToViewports` hides the actor unless `visibility: true`; the VOI synchronizer
  copies an overlay's window onto the base of views that don't have the overlay yet, so it is paused
  while a layer is added. Segmentation (#286): threshold the selected layer via `ctx.selectedLayer`.

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

## Entry contract (#279, decided in #184)

The viewer page `/projects/<project>/participants/<participant>/viewer/?series=<uid>&series=…`
(`viewer_url()` builds it; pseudonymized UIDs, so no PHI in the URL) is standalone, opens in a new tab
and is titled with the participant's alias. It 404s on anything the user can't see. Each load writes one
`viewer_open` audit entry under a Viewer Session id the page makes and hands over as `viewer-session`.

- `series-list`: id of the page's `<script type="application/json">` (`json_script`) with one entry per
  series (`SeriesEntry`: `study`, `series`, `modality`, `description`, `instances`,
  `frame_of_reference`, `open`). Opened series come first, in URL order: the first is the base, the rest
  are fused onto it at open (refusals say why, as on a drop). The rest are the participant's Related
  Series, from every study; Annotation/Segmentation series are never listed (the results tree shows
  them). Tests set `entries` directly.
- `participant`, `user` (drafts), `can-annotate`, `viewer-session`.

## Dev page

`/viewer/dev/?series=<uid>&related=<uid>,…` (pseudonymized UIDs, any participant): the same series list,
built by `dev_viewer_open`, for the browser harness. Login required, 404 unless DEBUG, no `viewer_open`.

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
