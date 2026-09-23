# Research: WSI viewing in Cornerstone3D vs. our WADO-RS endpoints

Resolves #186 (parent map #176). **Findings only; the recommendation at the end is input to the map, not a locked decision.**

Pinned sources (read 2026-09-23):
- **[cs3d]** cornerstonejs/cornerstone3D @ `d7760029` (core 5.10.10). Files: `packages/core/src/RenderingEngine/WSIViewport.ts`, `packages/core/src/utilities/WSIUtilities.ts`, `packages/core/src/RenderingEngine/GenericViewport/WSI/DicomMicroscopyRenderPath.ts`, `packages/core/examples/wsi/index.ts`, `utils/demo/helpers/createImageIdsAndCacheMetaData.js`, `packages/dicomImageLoader/src/imageLoader/wadors/{loadImage,getPixelData}.ts`, `packages/core/CHANGELOG.md`, `packages/docs/docs/migration-guides/5x/2-generic-viewport.md`.
- **[dmv]** ImagingDataCommons/dicom-microscopy-viewer @ `f1233f58` (v0.48.24; pins dicomweb-client 0.11.3, OpenLayers ^10.7). Files: `src/pyramid.js`, `src/metadata.js`, `src/viewer.js`, `src/utils.js`, `src/webWorker/decodeAndTransformTask.js`, `README.md`.
- **[dwc]** dcmjs-org/dicomweb-client (JS) `src/message.js`, `src/api.js`.
- **[ps18]** DICOM PS3.18 2026d, §8.7.3.3 / 8.7.3.3.2 (Bulk Data media types, Table 8.7.3-5) and §8.7.3.5 (media type syntax): https://dicom.nema.org/medical/dicom/current/output/chtml/part18/
- **[local]** `MiqaResearch/interfaces/http/api/views/dicom/wado.py`, `.../api/urls.py`, `MiqaResearch/tasks/dicom_handling/{records,metadata_dump,ndpi_conversion}.py`, `extractors/pathology.py`; pydicom 3.0.2, wsidicomizer 0.30.0 (`uv.lock`).
- **[exp]** One-liner run against the repo venv's pydicom 3.0.2 (not committed).

## 1. How Cornerstone3D shows WSI

- `ViewportType.WHOLE_SLIDE` → `WSIViewport`. It does **not** render tiles itself. It wraps `dicom-microscopy-viewer`'s `VolumeImageViewer` (OpenLayers under the hood) in a child div and syncs camera/zoom/annotations with CS3D [cs3d WSIViewport.ts:39-47, 607-619].
- `dicom-microscopy-viewer` is **not a dependency** of `@cornerstonejs/core`. The host app must supply it via `init({ peerImport })`; the default `peerImport` returns `null` [cs3d init.ts:86, 455; WSIUtilities.ts `getDicomMicroscopyViewer`]. The demo loads a prebuilt `dicomMicroscopyViewer.min.js` [cs3d utils/demo/helpers/initDemo.ts:89-94]. For our Vite build: bundle `dicom-microscopy-viewer` ourselves and wire `peerImport`. Its codecs are WASM (libjpeg-turbo, OpenJPEG, CharLS, OpenJPH) in web workers [dmv package.json:56-59].
- Setup, per the official example [cs3d examples/wsi/index.ts]:
  1. `client.retrieveSeriesMetadata({study, series})` (dicomweb-client).
  2. Build one `wadors:` imageId per instance **from the UIDs in the returned metadata** (`convertMultiframe: false`) [createImageIdsAndCacheMetaData.js:51-80].
  3. `client.getDICOMwebMetadata = imageId => wadors.metaDataManager.get(imageId)`, register `{imageIds, options:{webClient: client}}` as a display set, `viewport.setDisplaySets(...)`.
- `loadWSIData` wraps each instance's metadata in `VLWholeSlideMicroscopyImage`. It keeps only `ImageType[2]` = `VOLUME` or `THUMBNAIL` (so LABEL and OVERVIEW are dropped). Physical spacing comes from `ImagedVolumeWidth/Height ÷ TotalPixelMatrixColumns/Rows`. Orientation comes from `ImageOrientationSlide`, and the origin from `TotalPixelMatrixOriginSequence` [WSIUtilities.ts `getWSIImageDataMetadata`, `loadWSIData`]. Note that `ImageOrientationSlide.slice` is called before the null check, so a file without it throws.
- The viewer is constructed with `retrieveRendered: false`, `controls: ['overview','position']` [WSIViewport.ts:607-613]. `VolumeImageViewer` does not use `retrieveRendered` at all (it is not referenced in dmv `src/`).

## 2. DICOMweb requests actually made (CS3D WSI path)

| Request | Who | Needed? |
|---|---|---|
| `GET /studies/{s}/series/{se}/metadata` (Accept `application/dicom+json`) | CS3D example helper | **Yes.** It is the only metadata call. No QIDO is needed if the caller already has the study and series UIDs. |
| `GET /studies/{s}/series/{se}/instances/{i}/frames/{n}`: **one frame per request, one request per tile** | dmv tile loader [pyramid.js:377-500] | **Yes.** This is the hot path. |
| BulkDataURI fetch for `OpticalPathSequence[0].ICCProfile` | dmv `_getIccProfiles` [pyramid.js:29-66] | Only if metadata gives a `BulkDataURI`. `InlineBinary` is accepted too [metadata.js:273-305]. |
| `GET .../instances/{i}/rendered` (`image/png`) | dmv `OverviewImageViewer`/`LabelImageViewer` only [viewer.js:6791-6880] | **No** for `WSIViewport`. |
| `retrieveInstance` (P10) | dmv annotation (SR) loading [annotation.js:223] | No. It is not used by the CS3D viewport. |

Frame request details:
- Accept: `multipart/related; type="application/octet-stream"; transfer-syntax=*`. The code comment calls this "a hack to work around standard compliance issues of the Google Cloud Healthcare API" [pyramid.js:430-458].
- The dmv decoder **ignores the response Content-Type**. It sniffs the payload magic bytes: JPEG → libjpeg-turbo, `FFD9`-terminated → JPEG 2000, SOI+`F7`/`E8` → JPEG-LS, anything else → treated as raw uncompressed pixels [decodeAndTransformTask.js:100-160, 215-230].
- dicomweb-client finds the multipart boundary **from the body's first line**, not the header [dwc message.js `multipartDecode`].
- Tile→frame mapping [metadata.js:140-200]:
  - `TILED_FULL`: frame number is computed (row-major, per focal plane, per optical path). It needs only `Rows`, `Columns`, `TotalPixelMatrix*`, and `OpticalPathSequence`.
  - `TILED_SPARSE` (and the default when `DimensionOrganizationType` is absent): it needs `PerFrameFunctionalGroupsSequence[*].PlanePositionSlideSequence` in the metadata. Missing tiles are rendered blank/white, not fetched.
- Our converter output: wsidicomizer 0.30 writes the VL WSI IOD with a **Basic Offset Table by default** (`offset_table=OffsetTableType.BASIC`) [wsidicomizer.py `convert`; README `--offset-table`]. NDPI JPEG tiles are passed through unless re-encoding is requested, so expect JPEG-baseline encapsulated frames (not verified on a sample file).

## 3. Standard rules that matter [ps18]

- Frames in a compressed TS go out as `image/jpeg`, `image/jp2`, `image/jls`, `image/jphc`, … with a `transfer-syntax` parameter (Table 8.7.3-5). "**Compressed Bulk Data is never transferred using application/octet-stream.**" [§8.7.3.3.2]
- `application/octet-stream` means uncompressed pixels, default Explicit VR LE `1.2.840.10008.1.2.1` [§8.7.3.3, §8.7.3.3.1]. The exception: a server holding only lossy-compressed data may return that.
- `transfer-syntax=*` "only applies to compressed Transfer Syntaxes corresponding to the specified Media Type" [§8.7.3.3.2]. dmv's `octet-stream` + `*` is therefore off-standard, and servers in the wild answer it by returning the stored encoding.
- Multipart responses must carry `type` and `boundary` [§8.7.3.5.1].
- CS3D's regular (non-WSI) `wadors` loader **does** read the part `Content-Type`. It takes `transfer-syntax=` from it, or falls back to the media-type default. With `application/octet-stream` and no parameter, it assumes **Implicit VR LE (uncompressed)** [dicomImageLoader loadImage.ts:33-87; getPixelData.ts:59-66].

## 4. Gaps in `wado.py` (against the WSI path)

Ordered by severity:

1. **`/frames` is broken for every file today.** `ds.is_pixel_data_encapsulated` does not exist on pydicom 3.0.2's `Dataset`. It raises `AttributeError` inside the `try`, which becomes **HTTP 500** "Error extracting frame". The import `pydicom.encaps.utils` also fails (`encaps` is a module, not a package) [exp]. There is no test covering `/frames` (the only WADO test is `tests/test_dicom_ingestion_single_file.py:291`, a P10 retrieve).
2. **UID mismatch → 404s.** The DB stores HashUID pseudonyms (`records.py:54`, #115), but `/metadata` returns the **raw file header** (`pydicom.dcmread(...).to_json_dict()`). That header has the original Study, Series and SOP UIDs. CS3D builds imageIds from the metadata UIDs, and dmv builds frame URLs from `pyramid.metadata[z].StudyInstanceUID/SeriesInstanceUID/SOPInstanceUID` [pyramid.js:389-405]. Every frame URL then misses the pseudonymized lookup. The same header also carries **PHI** (PatientName and the like). `metadata_dump.py` already has the PHI-strip/pseudonymize rules, but they are not applied here.
3. **Whole file read per tile.** `pydicom.dcmread(f)` (no `stop_before_pixels` or `defer_size`) loads all of PixelData for **every** single-tile request. A level-0 WSI instance is often GBs, and dmv fires one request per tile, so the design can't work at WSI scale. With a BOT present (wsidicomizer default), the frame offsets are cheap to index once and serve with `seek`.
4. **Media type / transfer syntax wrong.** Compressed frames are labeled `application/octet-stream` with no `transfer-syntax`, which violates §8.7.3.3.2. dmv tolerates this because it sniffs the payload. CS3D's stack loader would **mis-decode** JPEG frames as raw pixels (relevant for any compressed CT/MR series the same viewer opens). There is no `Accept` negotiation, and transcoding isn't needed if we honour `*`.
5. **Native (uncompressed) fallback** decodes the whole `pixel_array` to return one frame. It is correct but O(file) memory. The offset is simply `index × Rows × Columns × SamplesPerPixel × BitsAllocated/8`.
6. `get_frame` is called without `number_of_frames`. With an empty BOT and multi-fragment frames it cannot split frames. Pass `NumberOfFrames`, or use `ExtendedOffsetTable` when present.
7. **Auth**: the router sits under `ClientCredentialsAuth(required_scopes=["read"])` (an OAuth client-credentials M2M flow) [urls.py:9-15]. A browser viewer needs a session or a user-bound token. This is owned by the "access control on WADO-RS" open item on #176.
8. Metadata endpoints re-open and re-parse every file per call (header only, which is acceptable). `TILED_SPARSE` pyramids return the full `PerFrameFunctionalGroupsSequence` (large but required). ICC profiles come out as `InlineBinary`: pydicom `to_json_dict` without a bulk-data handler inlines bytes, and dmv accepts that, so **no BulkData endpoint is needed**.

Not needed for WSI via CS3D: `/rendered`, `/thumbnail`, QIDO-RS, BulkData, and transcoding. Existing `/studies/.../metadata` and `/frames/{list}` routes are the right shape once fixed.

## 5. Maturity and limitations

- The WSI viewport was introduced in CS3D 1.78 (June 2024, "basic framework to display WSI images with annotations", #944). Later changes: ROI tools and the window-level tool (#2107, #2087), and DPR fixes (#1959, #2769) [CHANGELOG]. The 5.x Generic Viewport remaps `WHOLE_SLIDE` → `WHOLE_SLIDE_NEXT` through a "temporary migration layer" [migration-guides/5x/2-generic-viewport.md:36-60]. Expect API churn.
- The docs are thin: `viewports.md` says only "Suitable for rendering whole slide images". The example is the de-facto spec.
- Open upstream issues: #2690 WSI viewport cannot be re-enabled; #2754 annotation coordinates wrong unless DPR = 1; #2421 calibration not on WSI; #2480 `loadAndCacheImage` returns wrong frames for local multi-frame WSI.
- Rendering is OpenLayers/canvas inside dmv, not VTK. CS3D segmentation (labelmaps) is not wired to `WSIViewport`: only annotation tools render over it. Fusion and MPR do not apply.
- Supported codecs: baseline JPEG, JPEG 2000, JPEG-LS (plus HTJ2K via OpenJPH) [dmv README:35]. Float64 frames throw [pyramid.js:483].

## 6. Recommendation

- Use CS3D `WSIViewport` + a bundled `dicom-microscopy-viewer` via `peerImport`. It needs only **series metadata + single-frame retrieval**. Don't build `/rendered`, bulkdata or QIDO for this.
- Fix `wado.py` before the viewer work, as its own ticket:
  - (a) a working frame extractor that seeks by BOT/EOT offsets (or a per-instance offset index computed at ingest) and never loads the full PixelData;
  - (b) the part `Content-Type` set from the stored TS (`image/jpeg; transfer-syntax=1.2.840.10008.1.2.4.50`, etc.), honouring `transfer-syntax=*`, and `application/octet-stream; transfer-syntax=1.2.840.10008.1.2.1` only for native data;
  - (c) `/metadata` emitting DICOM JSON with UIDs **rewritten to the DB pseudonyms** and PHI stripped (reuse `metadata_dump.py` rules);
  - (d) tests for `/frames` and `/metadata` on a small `TILED_FULL` fixture.
- Treat CS3D WSI as **beta**: pin versions, and budget for the DPR/re-enable bugs and the `*_NEXT` migration.
