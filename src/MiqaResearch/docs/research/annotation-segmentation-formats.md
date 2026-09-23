# Research: storage formats for Cornerstone3D annotations and segmentations

Resolves issue #188 (parent map #176, DICOM viewer web component). **Findings plus a recommendation. The map decides.**

Pinned versions (latest on npm/PyPI, 2026-09-23): `@cornerstonejs/adapters` / `tools` **5.10.10** (adapters depends on `dcmjs` **0.52.0**), `highdicom` **0.28.1**, `dicom-microscopy-viewer` **v0.48.24**. Repo: `pydicom` 3.0.2.

Sources:
- **[PS3.4]** DICOM PS3.4 2026d, Storage SOP Classes, https://dicom.nema.org/medical/dicom/current/output/chtml/part04/sect_B.5.html
- **[PS3.3-ANN]** PS3.3 C.37 Microscopy Bulk Simple Annotations module, https://dicom.nema.org/medical/dicom/current/output/chtml/part03/sect_C.37.html (IOD: A.87)
- **[hd-seg] [hd-sr] [hd-ann]** highdicom docs: https://highdicom.readthedocs.io/en/latest/seg.html, `/tid1500.html`, `/ann.html`
- **[adp]** `@cornerstonejs/adapters@5.10.10` published `dist/esm` (read from the npm tarball). Paths relative to `dist/esm/adapters/Cornerstone3D/`.
- **[tl]** `@cornerstonejs/tools@5.10.10` `dist/esm/types/AnnotationTypes.d.ts`, `dist/esm/tools/annotation/`
- **[cs-save]** Cornerstone docs source `packages/docs/docs/concepts/cornerstone-tools/segmentation/saving.md` (cornerstonejs/cornerstone3D main)
- **[cs-wsi]** https://www.cornerstonejs.org/docs/api/core/classes/wsiviewport/
- **[ohif]** OHIF/Viewers main: `extensions/dicom-microscopy/src/DicomMicroscopyANNSopClassHandler.js`, `extensions/cornerstone-dicom-rt/src/loadRTStruct.js`
- **[dmv]** ImagingDataCommons/dicom-microscopy-viewer README
- **[repo]** this repo: `MiqaResearch/tasks/dicom_handling/extractors/__init__.py`, `MiqaResearch/interfaces/http/api/views/dicom/wado.py`

## 1. The options and their SOP classes

| Format | SOP Class UID [PS3.4] | Holds |
|---|---|---|
| DICOM SR, TID 1500 Measurement Report | Comprehensive 3D SR `1.2.840.10008.5.1.4.1.1.88.34` (Enhanced SR `.88.22` for 2D-only SCOORD) | measurements + ROIs as SCOORD (image coords) or SCOORD3D (Frame-of-Reference coords), qualitative evaluations, tracking identifiers/UIDs, references to SEG segments [hd-sr] |
| DICOM SEG | Segmentation Storage `…1.1.66.4` (BINARY/FRACTIONAL) | pixel masks, one frame set per segment, overlaps allowed [PS3.4, hd-seg] |
| DICOM Label Map SEG | Label Map Segmentation Storage `…1.1.66.7` (LABELMAP) | 8/16-bit label image, all segments in one frame set, **no overlaps**; added to the standard 2024 [PS3.4, hd-seg] |
| RTSTRUCT | RT Structure Set Storage `…1.1.481.3` | planar contours per ROI in patient coords (ROIContourSequence) |
| Microscopy Bulk Simple Annotations (ANN) | `…1.1.91.1` | large arrays of POINT/POLYLINE/POLYGON/ELLIPSE/RECTANGLE, grouped, with per-annotation float measurements [PS3.3-ANN, hd-ann] |
| Cornerstone native JSON | n/a | `Annotation` objects: `metadata` (a `ViewReference`: toolName, FrameOfReferenceUID, referencedImageId, camera), `data.handles.points` / `data.contour.polyline` as world `Point3`, `cachedStats`, label, parent/child/interpolation UIDs, `predecessorImageId` [tl]. Segmentation state is metadata only; labelmap voxels live in image/volume buffers. |

## 2. What `@cornerstonejs/adapters` (and dcmjs) can do

Adapters moved from dcmjs into cornerstone3D in 2023; `Cornerstone3D` adapters use dcmjs for dataset building/writing [adp `package.json`; cornerstonejs.org/docs/api/adapters].

**SR (TID 1500), both directions** — `Cornerstone3DSR.MeasurementReport.generateReport(toolState, metadata, options)` / `generateToolState(dataset, sopInstanceUIDToImageIdMap, metadata, hooks)` [adp `MeasurementReport.d.ts`].
- Writes Comprehensive 3D SR (`report.dataset.SOPClassUID = …Comprehensive3DSR`) [adp `MeasurementReport.js:401`]. Reader throws unless TID 1500: `'This package can currently only interpret DICOM SR TID 1500'` [:410].
- Tool adapters shipped: Length, Bidirectional, Angle, CobbAngle, CircleROI, EllipticalROI, RectangleROI, PlanarFreehandROI, ArrowAnnotate, Probe, UltrasoundDirectional, KeyImage [adp `index.d.ts`].
- **Tools without an adapter are silently dropped on export**: `getMeasurementGroup` returns `undefined` when `measurementAdapterByToolType` has no entry [adp `MeasurementReport.js:72-77`]. Tools in `@cornerstonejs/tools` with no SR adapter include SplineROI, LivewireContour, Label, Height, DragProbe, ETDRSGrid and the contour-segmentation tools [tl `tools/annotation/`]. Custom adapters can be registered (`registerTool`, `registerTrackingIdentifier`).
- Round-trip key: each measurement group carries TrackingIdentifier `Cornerstone3DTools@^0.1.0:<ToolName>` (`CORNERSTONE_3D_TAG`) [adp `cornerstone3DTag.d.ts`]. On import the adapter is chosen by a `hooks.getToolClass` hook, else by tracking identifier, else by graphic type/point count (`getAdapterForCodeType`) — so third-party TID 1500 SRs load as generic shapes [adp `MeasurementReport.js:428`]. Unparseable groups are skipped with a `warn` [:440].
- What survives: geometry (SCOORD in image pixel coords, or SCOORD3D in world coords when the annotation has no imageId), NUM measurements + units, finding/finding-site codes, label/comment text, text-box position, freehand control points [adp `MeasurementReport.d.ts`, `PlanarFreehandROI.js`]. What does not: view/camera state, lock/visibility/colour, parent/child/interpolation links, tool-specific fields not modelled by the adapter (inference from the adapter shape; not exhaustively tested).

**SEG, both directions** — `Cornerstone3DSEG.Segmentation.generateSegmentation(images, labelmaps, metadata, options)`; import via `createFromDICOMSegBuffer` / `createFromDicomSegImageId` / `generateToolState` [adp `Segmentation/*.d.ts`].
- Default export is **bitmap SEG `…66.4`, BINARY**, one segment per frame, 1-bit packed; `options.sopClassUID = '…66.7'` exports **LABELMAP** (8-bit, 16-bit if >255 segments). Overlapping voxels on LABELMAP export: `"the later labelmap wins"` with a warning [adp `Segmentation/generateSegmentation.js:150-230, 252-297`].
- Only non-empty frames are written; export refuses frames whose source SOP Instance UID cannot be resolved [same file].
- Transfer syntaxes: Explicit VR LE (default) or **RLE Lossless** only; anything else throws `Unsupported compressed transfer syntax for SEG encoding` [adp `encodePixelData.js:404`].
- Import handles BINARY, FRACTIONAL (pseudo-binary check) and LABELMAP [adp `Segmentation/labelmapImagesFromBuffer.js:467, 743`].
- Revisions: `options.predecessorImageId` puts the new object in the predecessor's series with `InstanceNumber+1` and `PredecessorDocumentsSequence`; without it a new series `Research Derived series`, number 99 [cs-save]. Same option on SR `generateReport` and RTSS.
- Source images must be pixel images with `voxelManager` scalar data (`image.voxelManager.getScalarData()`) resolved through the metadata provider [adp `generateSegmentation.js` `_createMultiframeSegmentationFromReferencedImages`]. No tiled/WSI output path (no TILED_FULL/TILED_SPARSE handling in the adapter; grep found none).

**RTSTRUCT, export only** — `Cornerstone3DRT.RTSS.generateRTSSFromRepresentation/Labelmap/Contour/Annotations` [adp `RTStruct/RTSS.d.ts`]. No RTSTRUCT reader in adapters; loading is done by OHIF's `extension-cornerstone-dicom-rt/loadRTStruct.js` (ROIContourSequence → contour segmentation) [ohif]. Labelmap → RTSS goes through contour extraction, so it is lossy (voxel mask → polygons).

**ANN: nothing.** No reference to `…91.1` or bulk annotations in cornerstone3D (GitHub code search) or adapters [adp]. OHIF reads ANN only via its dicom-microscopy extension (`DicomMicroscopyANNSopClassHandler`, overlay display set, newest instance wins) [ohif]. `dicom-microscopy-viewer` displays SEG, Parametric Map, Comprehensive 3D SR and ANN overlays and draws ROIs as SCOORD3D [dmv].

**highdicom (Python, server side)** reads and writes SEG (BINARY/FRACTIONAL/LABELMAP since 0.24.0; tiled `TILED_FULL`/`TILED_SPARSE`, pyramids via `create_segmentation_pyramid`; JPEG2000/JPEG-LS/RLE lossless) [hd-seg], TID 1500 SR (`Comprehensive3DSR`, planar/volumetric ROI groups, SEG segment references) [hd-sr], and ANN (`MicroscopyBulkSimpleAnnotations`, `annread`) [hd-ann]. It does not write RTSTRUCT.

## 3. WSI (pathology)

- Cornerstone `WSIViewport` wraps `dicom-microscopy-viewer` (peer import) and "accepts standard CS3D annotations" [cs-wsi]; annotations there use slide/world coordinates (`indexToWorldWSI`). So SR export via SCOORD3D is the viable Cornerstone path; this is also what Slim/dicom-microscopy-viewer store (Comprehensive 3D SR with SCOORD3D) [dmv].
- SR is inefficient for many ROIs: ANN exists because it stores "large number of similar annotations or measurements in efficient arrays without duplication of the descriptive metadata" [hd-ann]. ANN coordinates are 2D (per frame / total pixel matrix, needs Referenced Image Sequence) or 3D (Frame of Reference; "more easily used with any image in the pyramid"); OF (float32) or OD (float64) flat arrays; groups carry property category/type codes and generation type MANUAL/SEMIAUTOMATIC/AUTOMATIC [PS3.3-ANN, hd-ann].
- WSI segmentation masks: only highdicom produces tiled SEG. Cornerstone adapters cannot (see §2), so drawing labelmaps on WSI in the browser has no DICOM export path today.

## 4. Size (arithmetic estimates, not measured)

- CT 512×512, 5 segments over 80 slices each. BINARY SEG: 32 KiB/frame × 400 frames ≈ **13 MB** uncompressed. LABELMAP 8-bit: 256 KiB × 80 ≈ 21 MB raw, but RLE compresses mostly-zero frames by ~an order of magnitude or more; highdicom cites LABELMAP as up to "2 orders of magnitude" smaller than BINARY [hd-seg]. The Cornerstone adapter's only compression is RLE.
- WSI 100k×80k px: a full-extent BINARY mask is 1 GB/segment uncompressed; TILED_SPARSE with empty tiles omitted scales with the covered area [hd-seg].
- 100k nuclei polygons × 16 vertices: ANN ≈ 100k×16×2×4 B ≈ **13 MB** (+0.4 MB index). The same in SR is one nested content-item tree per ROI; impractical at that count.
- Cornerstone JSON: world points as text ≈ 50–60 B/point plus `cachedStats`; fine for tens–hundreds of radiology annotations; unsuitable for voxel data without a binary sidecar.

## 5. Comparison

| | Round-trip with Cornerstone | Interoperability | WSI | Size |
|---|---|---|---|---|
| SR TID 1500 (C3D SR) | Good for 12 supported tools (tracking id); unsupported tools dropped silently; UI state lost | High: Slim/dicom-microscopy-viewer, highdicom, dcmjs; OHIF/Slicer/dcmqi assumed, not verified here | Yes via SCOORD3D, small ROI counts | Small per ROI, scales badly beyond ~10³ |
| SEG BINARY `66.4` | Good (adapter default, both directions) | Highest of the mask formats | Tiled only via highdicom | Largest; RLE or none from browser |
| SEG LABELMAP `66.7` | Good (adapter opt-in); overlaps lost | New (2024); limited viewer support [hd-seg]; pydicom 3.0.2 has no name for the UID | Via highdicom | Smallest compressed |
| RTSTRUCT | Export only in adapters; import needs OHIF code; mask→contour lossy | RT/TPS systems | No | Small (contours) |
| ANN `91.1` | None in Cornerstone | Slim/dicom-microscopy-viewer, OHIF microscopy, highdicom | Built for it | Compact flat arrays |
| Cornerstone JSON | Lossless for Cornerstone state (incl. UI state) | None; imageIds embed our WADO URLs and UIDs; tied to Cornerstone version | Works in WSIViewport | Small for annotations; no voxels |

## 6. Repo-specific findings

- **Re-ingestion**: the SOP-class extractor registry has handlers for RTSTRUCT (radiotherapy), RDSR, WSI and standard images; SEG, Label Map SEG, Comprehensive 3D SR and ANN currently fall through to `generic.extract` [repo `extractors/__init__.py`]. They would still ingest, but without reference extraction (the RTSTRUCT handler pseudonymizes referenced UIDs; nothing does that yet for SEG `ReferencedSeriesSequence`/`SourceImageSequence` or SR evidence sequences).
- **UIDs/PHI in derived objects**: WADO-RS metadata endpoints return `pydicom.dcmread(...).to_json_dict()` of the stored bytes [repo `wado.py:81-120`], i.e. original UIDs and whatever patient/study tags the stored file has (#115). Adapters copy study/patient/series data from that metadata into the derived object (`STUDY_DATA`/`SERIES_DATA`/`IMAGE_DATA` merge in `generateSegmentation.js`), so a browser-built SEG/SR references original UIDs and inherits those tags. Persisting it must go through the ingestion PHI/UID path, or the metadata served to the viewer must be pseudonymized first.

## 7. Recommendation

1. **Canonical store = DICOM derived objects**, written as new instances in the Research Project and re-ingested through the pipeline: **SEG `66.4` BINARY** for segmentations (adapter default, widest support, RLE); **Comprehensive 3D SR TID 1500** for radiology annotations/measurements. Use `predecessorImageId` for revisions (gives versioning/authorship chain via series + `PredecessorDocumentsSequence`).
2. Offer **LABELMAP `66.7`** later as an opt-in for large multi-segment non-overlapping masks, once consumers are confirmed.
3. **WSI**: Comprehensive 3D SR with SCOORD3D for manual ROIs from `WSIViewport` (Slim-compatible). Bulk/AI annotations as **ANN**, written server side with highdicom; the browser can display ANN only through dicom-microscopy-viewer, not Cornerstone tools. No browser WSI segmentation masks for now.
4. **RTSTRUCT**: not a primary format; export-only for RT interoperability if a project asks.
5. **Cornerstone JSON**: not the record. Acceptable only as an autosave/draft or for tool types with no SR adapter (or write custom adapters instead).
6. Before implementation: add registry handlers for SEG/SR/ANN reference extraction, and resolve the original-UID/PHI exposure in WADO metadata (§6).
