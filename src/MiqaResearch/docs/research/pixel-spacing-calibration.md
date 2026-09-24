# Research: 2D pixel spacing sources and Cornerstone3D calibration signalling

Resolves issue #199 (parent map #176). **Findings only, no design decisions.**

Pinned version: **Cornerstone3D 5.10.11** (`@cornerstonejs/core`, `tools`, `metadata`, `dicom-image-loader`, all 5.10.11, as installed by the #185/#191 spikes under `.dev-data/webcomponents/node_modules/@cornerstonejs/`).

Sources:
- **[src]**: the installed `dist/esm` JS. Paths below are relative to `node_modules/@cornerstonejs/`. In 5.10 the spacing logic lives in **`@cornerstonejs/metadata`**. `core` re-exports it (`core/dist/esm/utilities/getPixelSpacingInformation.js`, `core/dist/esm/enums/CalibrationTypes.js`).
- **[dicom]**: DICOM PS3.3 (current). §10.7 Basic Pixel Spacing Calibration Macro (PixelSpacing / PixelSpacingCalibrationType), §C.8.11.4 DX Detector module (ImagerPixelSpacing), §C.8.5.5 US Region Calibration module (SequenceOfUltrasoundRegions), §C.8.12.4 Whole Slide Microscopy Image module (ImagedVolumeWidth/Height). <https://dicom.nema.org/medical/dicom/current/output/chtml/part03/>
- **[repo]**: `MiqaResearch/tasks/dicom_handling/`, `MiqaResearch/interfaces/http/api/views/dicom/wado.py`, installed `wsidicom`.

## 1. Answer

- **2D stack spacing comes from the IMAGE_PLANE metadata module.** For projection X-ray SOP classes it is picked by `getPixelSpacingInformation`. All other SOP classes use `PixelSpacing` (0028,0030) as is. When there is no spacing, the fallback is 1×1 and the unit is `px`.
- **The calibration kind reaches the tools through `calibratedPixelSpacing` metadata**, which holds `{rowPixelSpacing, columnPixelSpacing, type, scale?}`. `StackViewport` merges it into `getImageData().calibration`. `getCalibratedLengthUnitsAndScale` then adds `calibration.type` to the unit string, e.g. `12.3 mm ERMF`. Ultrasound uses a separate channel: the image's `calibration.sequenceOfUltrasoundRegions` (CALIBRATION module), shown as `cm US Region`.
- **Pitfall.** The ERMF/ImagerPixelSpacing logic runs only in the new *typed* metadata path (metadata added via `utilities.addDicomWebInstance` from `@cornerstonejs/metadata`). If the viewer fills the legacy `wadors.metaDataManager` instead, as in the classic `createImageIdsAndCacheMetaData` example pattern, the legacy wadors provider answers IMAGE_PLANE. That provider reads **only** `PixelSpacing`. No `calibratedPixelSpacing` entry is created, so there is no label, and a CR/DX that has only ImagerPixelSpacing is measured in `px`. (Confirmed by reading the code: provider-chain order and code paths. Not yet exercised in a browser.)

## 2. `getPixelSpacingInformation(instance)` [src `metadata/dist/esm/utilities/getPixelSpacingInformation.js`]

Input: a naturalized instance (`PixelSpacing`, `ImagerPixelSpacing`, `SOPClassUID`, `PixelSpacingCalibrationType`, `EstimatedRadiographicMagnificationFactor`, `DistanceSourceToDetector`, `DistanceSourceToPatient`/`DistanceSourceToEntrance`).
Returns `{ PixelSpacing, type: CalibrationTypes, isProjection }`.

- **Non-projection SOP class** (CT, MR, US, SC, NM, PT, …): `{ PixelSpacing, type: NOT_APPLICABLE (""), isProjection: false }`. PixelSpacing is used unchanged, and may be undefined.
- **Projection SOP classes** (hard-coded set): CR `.1`, DX `.1.1`/`.1.1.1`, MG `.1.2`/`.1.2.1`, IO `.1.3`/`.1.3.1`, XA `.12.1`, Enhanced XA `.12.1.1`, XRF `.12.2`, Enhanced XRF `.12.2.1`, XA bi-plane `.12.3`. These go to `calculateRadiographicPixelSpacing`, which checks the cases in this order:
  1. `PixelSpacing` + `PixelSpacingCalibrationType == "GEOMETRY"` → PixelSpacing, type **ERMF**. It logs a warning if PixelSpacing equals ImagerPixelSpacing.
  2. `PixelSpacing` + `PixelSpacingCalibrationType == "FIDUCIAL"` → PixelSpacing, type **CALIBRATED**.
  3. `ImagerPixelSpacing` is present, so `getERMF` is computed:
     - `ERMF > 1`, or else `SID/SOD` when `DistanceSourceToPatient` (falling back to `DistanceSourceToEntrance`) is less than `DistanceSourceToDetector` → **ImagerPixelSpacing / ERMF**, type **ERMF**.
     - `ImagerPixelSpacing[0] > PixelSpacing[0]`, meaning the modality has already corrected PixelSpacing → PixelSpacing, type **ERMF**.
     - otherwise → `PixelSpacing ?? ImagerPixelSpacing`, type **PROJECTION** (`"Proj"`). This is spacing at the detector plane, so it overstates anatomy by the magnification factor.
  4. No ImagerPixelSpacing → PixelSpacing (may be undefined), type **UNKNOWN**.
- DICOM semantics [dicom §10.7, §C.8.11.4]: ImagerPixelSpacing (0018,1164) is measured at the detector front plane. PixelSpacing in a projection image is "in the patient" only when PixelSpacingCalibrationType (0028,0A02) says so: GEOMETRY means corrected by ERMF (0018,1114), FIDUCIAL means calibrated against an object of known size. Without either, the true size at the patient is unknown.

## 3. `calibratedPixelSpacingMetadataProvider` [src `metadata/dist/esm/utilities/calibratedPixelSpacingMetadataProvider.js`]

- A module-level `Map` keyed by image URI (the imageId without its frame suffix). API: `add(imageId, payload)` (also clears the cached IMAGE_PLANE query), `get('calibratedPixelSpacing', imageId)`, `clear()`. `registerDefaultProviders` registers `get` as a plain provider at priority 0.
- Payload shape (`Types.IImageCalibration`): `{ rowPixelSpacing?, columnPixelSpacing?, scale?, aspect?, type, tooltip?, sequenceOfUltrasoundRegions? }`.
- It is filled in two ways:
  - **automatically**: the typed IMAGE_PLANE provider `getImagePlaneCalibrated` [src `metadata/.../metadataProvider/imagePlaneCalibrated.js`] calls `getPixelSpacingInformation`. When it gets a PixelSpacing back, it adds `{rowPixelSpacing, columnPixelSpacing, type}` unless an entry already exists. So a user calibration survives a reload of the image.
  - **by the user**: `tools.utilities.calibrateImageSpacing(imageId, renderingEngine, calibrationOrScale)` [src `tools/dist/esm/utilities/calibrateImageSpacing.js`]. A bare number becomes `{type: USER, scale}`. It writes to the provider, then calls `viewport.calibrateSpacing(imageId)` to reload the image.
- `StackViewport.calibrateIfNecessary` reads it, sets `hasPixelSpacing = scale > 0 || (!usingDefaultValues && rowPixelSpacing > 0)`, and fires **`Events.IMAGE_SPACING_CALIBRATED`** with `{imageId, calibration, scale, imageData, worldToIndex}` when the calibration object changes [src `core/.../StackViewport.js`]. `getImageData()` returns `calibration: {...csImage.calibration, ...viewport.calibration}`.

## 4. CalibrationTypes and how tools show them

Enum [src `metadata/dist/esm/enums/CalibrationTypes.js`]: `NOT_APPLICABLE ""`, `ERMF "ERMF"`, `USER "User"`, `PROJECTION "Proj"`, `REGION "Region"`, `ERROR "Error"`, `UNCALIBRATED "Uncalibrated"`, `CALIBRATED "Calibrated"`, `UNKNOWN "Unknown"`.

`getCalibratedLengthUnitsAndScale(image, handles)` [src `tools/dist/esm/utilities/getCalibratedUnits.js`] is used by Length, Bidirectional, Rectangle/Ellipse/Circle/Planar-freehand ROI and similar tools:
- Base unit: `mm` if `hasPixelSpacing`, else `px`. Area: `mm²` or `px²`. Volume: `mm³` or `voxels`.
- Scale: `calibration.scale` (USER), or else 1 / (`calibration.column|rowPixelSpacing` or the image spacing).
- A suffix is added only for types in `[ERMF, USER, ERROR, PROJECTION, CALIBRATED, UNKNOWN]`. Examples: `mm ERMF`, `mm User`, `mm Proj`, `mm Calibrated`, `mm Unknown`, `mm² Proj`. NOT_APPLICABLE (all cross-sectional images) shows a plain `mm`. `REGION` is never used as a suffix.
- `UNCALIBRATED` forces `px` / `px²` / `voxels`, even when spacing exists.
- **US regions**: the first region that contains *all* handles and has RegionDataType 1–4 (tissue, colour flow, PW/CW spectral) or a supported unit pair. If X and Y units match, scale = 1/|PhysicalDelta| and the unit comes from PhysicalUnits (3 = `cm`, 4 = `seconds`, …). The label is `cm US Region`, or `ECG Region` when the Y unit is −1. A measurement that crosses a region boundary falls back to the image spacing: `px` for US, which has no PixelSpacing. `getCalibratedProbeUnitsAndValue` gives Probe per-axis values (e.g. cm/sec vs. seconds in Doppler).
- Tools render text as `` `${roundNumber(length)} ${unit}` `` [src `tools/.../annotation/LengthTool.js`], so the kind of calibration is visible to the user only through the unit suffix. Stats also carry `unit`/`areaUnit` in `cachedStats` and in `statsArray` (`namedLength.unit`), where SR export can read it.

## 5. Per-case summary

| Case | Spacing used | `calibration.type` | Tool label |
|---|---|---|---|
| CT/MR/PT/NM (cross-sectional) | PixelSpacing | `""` | `mm` |
| CR/DX/MG/XA with PixelSpacing + CalibrationType GEOMETRY | PixelSpacing | ERMF | `mm ERMF` |
| … + CalibrationType FIDUCIAL | PixelSpacing | Calibrated | `mm Calibrated` |
| … ImagerPixelSpacing + ERMF>1 (or SID/SOD) | ImagerPixelSpacing / ERMF | ERMF | `mm ERMF` |
| … ImagerPixelSpacing only (or equal to PixelSpacing) | ImagerPixelSpacing (detector plane) | Proj | `mm Proj` |
| … no ImagerPixelSpacing, PixelSpacing only | PixelSpacing | Unknown | `mm Unknown` |
| … no spacing at all | 1×1 default | Unknown, no entry | `px` |
| US with SequenceOfUltrasoundRegions | region PhysicalDelta (cm) | via regions | `cm US Region` (inside one region), else `px` |
| SC / VL photo / OT without PixelSpacing | 1×1 default (`usingDefaultValues`) | none | `px` |
| SC with PixelSpacing | PixelSpacing | `""` | `mm`, **no warning**. CS3D ignores NominalScannedPixelSpacing (0018,2010) and does not check that SC spacing is meaningful. |
| User calibration (any) | `scale` | User | `mm User` |
| WSI (SM) | `ImagedVolumeWidth / TotalPixelMatrixColumns` (and Height/Rows) | none | `mm` |

**WSI** [src `core/dist/esm/utilities/WSIUtilities.js` `getWSIImageDataMetadata`, `RenderingEngine/WSIViewport.js`]: WSI does not use the IMAGE_PLANE/calibration path. Spacing is read from the instance with the most frames (the base level): `ImagedVolumeWidth/Height` (mm) divided by `TotalPixelMatrixColumns/Rows`. `hasPixelSpacing = !!(width && height)`. `calibration` stays undefined, so tools show plain `mm` (sub-mm values, µm are not used). The Pixel Measures functional-group PixelSpacing is not used. dicom-microscopy-viewer has its own scale bar.

## 6. What we ingest [repo]

- Ingestion never rejects a SOP class. The registry `tasks/dicom_handling/extractors/__init__.py` falls back to `generic`. `standard_image.STANDARD_IMAGE_SOP_CLASSES` lists DX (both), CT/MR (+ enhanced/legacy), US single-frame `.6.1`, SC (all five), XA, XRF, NM, PET. The monitor filter offers CT, MR, PT, US, XA, DX, MG and RT*. Pathology SM comes in as native DICOM or as NDPI converted with `wsidicomizer`. `wsidicom` writes `ImagedVolumeWidth/Height` (`wsidicom/instance/dataset.py`), so CS3D WSI spacing works for converted slides.
- Which case each modality hits:
  - **DX, CR, MG, XA/XRF** → the projection path. Whether it shows ERMF, Proj or Unknown depends on the vendor's tags (ERMF, PixelSpacingCalibrationType, ImagerPixelSpacing).
  - **US** (`.6.1`; multi-frame `.3.1` goes to generic) → regions, else `px`.
  - **SC** (incl. screenshots and scanned docs) → `px`, or an unverified `mm` if PixelSpacing is present.
  - **CT/MR/PT/NM** → `mm`.
  - **SM** → WSI path.
- The WADO-RS `/metadata` endpoints return `ds.to_json_dict()` of the whole file (`wado.py`). The PHI denylist (`phi.py`) does not touch spacing tags. So ImagerPixelSpacing, ERMF, PixelSpacingCalibrationType and SequenceOfUltrasoundRegions reach the client. The #190 sanitizer must keep them.
- The ingest DB column `pixel_spacing` stores only `PixelSpacing` (`extractors/common.py:image_geometry`). It does not hold ImagerPixelSpacing or US regions. That is fine because the viewer reads WADO metadata, but the column is not a calibration source.
- **Side finding (bug, out of scope here):** `STANDARD_IMAGE_SOP_CLASSES` has `1.2.840.10008.5.1.4.1.1.9` commented "Computed Radiography". That UID is retired *Standalone Curve Storage*. CR is `1.2.840.10008.5.1.4.1.1.1`. MG (`.1.2`/`.1.2.1`) and US multi-frame (`.3.1`) are also missing. These files still go through the generic extractor, so the only effect is that their geometry columns are null.

## 7. Open points for design (not decided here)

- Use the typed metadata path (`addDicomWebInstance`) so that ERMF/Proj/US handling applies. Otherwise we need our own IMAGE_PLANE/calibration provider. A prototype should check CR/DX `mm Proj`/`mm ERMF` labels and US `cm US Region` in the browser.
- Whether to add a warning or refuse `mm` for SC/OT, and whether to offer user calibration (`calibrateImageSpacing`, type USER), plus how that is persisted in SR (#188/#189).
- Whether `Proj`/`Unknown`/`US Region` should be relabelled for users (the raw suffixes are terse), e.g. by wrapping `getCalibratedLengthUnitsAndScale` or post-processing `cachedStats.unit`.
