# Cornerstone3D: single-plane / three-view MPR with crosshairs, and CT/MR + PET fusion

Research for [#187](https://github.com/SPRINTR-PC/miqa-research/issues/187) (map [#176](https://github.com/SPRINTR-PC/miqa-research/issues/176)).

Sources read at pinned commits:

- Cornerstone3D `cornerstonejs/cornerstone3D` @ `d7760029` (packages at **v5.10.10**) — `CS3D` below.
  Permalink base: `https://github.com/cornerstonejs/cornerstone3D/blob/d7760029146e55427f2510485192bce0ea4d697f/`
- OHIF `OHIF/Viewers` @ `aafb6e8f` (**v3.14.0-beta.35**) — `OHIF` below.
  Permalink base: `https://github.com/OHIF/Viewers/blob/aafb6e8f5fd272a4d2a61a8dbc69ab523d955301/`
- `cornerstonejs/calculate-suv` @ `main` (`src/calculateSUVScalingFactors.ts`, `src/calculateScanTimes.ts`, `src/calculateStartTime.ts`); pinned by CS3D as `1.0.3` (`packages/metadata/package.json`).
- DICOM PS3.3 C.8.9 (PET modules): https://dicom.nema.org/medical/dicom/current/output/chtml/part03/sect_C.8.9.html ; PS3.18 (DICOMweb) ch. 8 / Table 8.7.3-5 for frame media types and `transfer-syntax` parameter: https://dicom.nema.org/medical/dicom/current/output/chtml/part18/chapter_8.html
- Local: `src/MiqaResearch/MiqaResearch/interfaces/http/api/views/dicom/wado.py`, `.../tasks/dicom_handling/metadata_dump.py`, `.../tasks/dicom_handling/phi.py`, `.../data/models/dicom_file.py`.

## 1. Single axial / sagittal / coronal stack

- A series becomes a volume via `volumeLoader.createAndCacheVolume(volumeId, { imageIds })` (default scheme `cornerstoneStreamingImageVolume`), then `volume.load()` streams the slices. (CS3D `packages/tools/examples/crossHairs/index.ts`)
- Display in a viewport of type `ViewportType.ORTHOGRAPHIC` with `defaultOptions.orientation = Enums.OrientationAxis.AXIAL | SAGITTAL | CORONAL` (also `ACQUISITION`, `*_REFORMAT`). (CS3D `packages/core/src/enums/OrientationAxis.ts`, crossHairs example)
- `ViewportType.STACK` only shows the acquisition plane; any reformat (sag/cor from an axial CT) needs the volume path. (CS3D `packages/core/src/enums/ViewportType.ts` doc comments)
- Volume geometry comes from the first image's `imagePixelModule`, `imagePlaneModule`, `generalSeriesModule`, `voiLutModule` (`makeVolumeMetadata.ts`); slices are sorted by projecting each `ImagePositionPatient` on the normal of `ImageOrientationPatient` (`sortImageIdsAndGetSpacing.ts`). With `wadors:` imageIds all per-instance metadata must be in cache **before** creating the volume. Missing IOP/IPP/PixelSpacing silently fall back to identity / `[0,0,0]` / `1 mm` (`dicomImageLoader/src/imageLoader/wadors/metaData/metaDataProvider.ts`, `IMAGE_PLANE` branch) — geometry would be wrong, not error.
- OHIF's gate for "can this series be a volume" (`platform/core/src/utils/isDisplaySetReconstructable.js`): >1 frame, all instances have IPP, same Rows/Columns/SamplesPerPixel/IOP, not all at one location, slice spacing uniform within 20% tolerance (gaps allowed, reported as missing frames), multiframe needs PixelMeasures/PlaneOrientation/PlanePosition. Worth copying as our "volume-capable" rule.

### v5 "Generic Viewport" note
CS3D 5.x adds `PLANAR_NEXT` etc. and an opt-in `init({ rendering: { useGenericViewport: true } })` that remaps `ORTHOGRAPHIC` → `PLANAR_NEXT` through compatibility adapters; the guide says legacy helpers (`setVolumes()` …) "should be expected to be removed in a later breaking release". The legacy enum is marked `@deprecated` but is still what all crosshairs/PET-CT examples use. (CS3D `packages/docs/docs/migration-guides/5x/2-generic-viewport.md`)

## 2. Three synchronized views with Crosshairs

Pattern (CS3D `packages/tools/examples/crossHairs/index.ts`):

1. Three `ORTHOGRAPHIC` viewports (axial/sagittal/coronal) in one `RenderingEngine`.
2. `setVolumesForViewports(renderingEngine, [{ volumeId, callback }], [ax, sag, cor])`.
3. One `ToolGroup`; **add the three viewports before activating the tool** ("For the crosshairs to operate, the viewports must currently be added ahead of setting the tool active").
4. `toolGroup.addTool(CrosshairsTool.toolName, { getReferenceLineColor, getReferenceLineControllable, getReferenceLineDraggableRotatable, getReferenceLineSlabThicknessControlsOn })`, then `setToolActive` on primary mouse.
- Crosshairs give: click/drag moves the centre (scrolls the other views), drag a reference line, rotate axes (oblique MPR), slab-thickness handles (MIP/MinIP/AvgIP via `viewport.setBlendMode`), optional `createSlabThicknessSynchronizer`. Minimal styles via `CrosshairsTool.minimalModeExamples`.
- Constraint: "Crosshairs currently only supports 3 viewports for a toolgroup" — for more (e.g. CT row + PET row + fusion row) use one tool group per trio plus camera-position synchronizers. (CS3D `packages/tools/examples/petCt/index.ts`)
- Single-plane mode needs no crosshairs; the same component can switch layouts by re-assigning the one cached volume to 1 or 3 viewports (volume cached once, shared).

## 3. Fusion (CT/MR + PET) in one viewport

- Pass two volumes to the same viewport; the order is back→front: `setVolumesForViewports(re, [{ volumeId: ctId, callback: ctTF }, { volumeId: ptId, callback: petColormapTF }], [fusionAx, fusionSag, fusionCor])`. (CS3D `petCt/index.ts`)
- **Same Frame of Reference is enforced**: `BaseVolumeViewport._isValidVolumeInputArray` throws `"Volumes being added to viewport … do not share the same FrameOfReferenceUID. This is not yet supported"`. No registration/resampling happens; world coords from IPP/IOP align the two grids (different resolutions are fine).
- Colormap + opacity per volume: `viewport.setProperties({ colormap: { name: 'hsv', opacity: 0.5 | [{value, opacity}…], threshold? }, voiRange: { lower, upper } }, ptVolumeId)`. `opacity` scalar = global fusion slider, `opacityMapping` = per-value ramp; rendered = opacity × mapping(v). (CS3D `packages/core/src/RenderingEngine/BaseVolumeViewport.ts` `setColormap`/`setProperties(…, volumeId)`, `packages/core/src/types/Colormap.ts`)
- Reference values: CS3D demo PET colormap `hsv`, mapping range 0–5 SUV, opacity ramp 0→0, 0.1→0.9, 5→1 (`utils/demo/helpers/setPetColorMapTransferFunctionForVolumeActor.js`); OHIF TMTV fusion `hsv` with ramp 0→0, 0.1→0.8, 1→0.9 and PET VOI from `getPTVOIRange` (`extensions/tmtv/src/utils/hpViewports.ts`). PET-only views are rendered inverted grey, range 0–5 SUV (`setPetTransferFunctionForVolumeActor.js`).
- Crosshairs slab/MIP in fusion: `filterActorUIDsToSetSlabThickness: [ctVolumeId]` restricts slab changes to one actor (petCt example).
- Sync: `createVOISynchronizer(id, { syncColormap: false })` for CT W/L and PET threshold between stand-alone and fusion viewports; `createCameraPositionSynchronizer` per plane.
- ROI stats in fusion viewport can be targeted to the PET volume only (petCt example, `roiToolNames` config).

## 4. SUV scaling

- Mechanism: loader pre-scales pixels. `getScalingParameters(imageId)` reads `modalityLutModule` (RescaleSlope/Intercept) and, if `Modality == 'PT'`, `scalingModule.suvbw/suvlbm/suvbsa`; `scaleArray` does `suvbw * (px * slope + intercept)`. Volume records `scaling.PT.suvbw`, `suvbwToSuvlbm`, `suvbwToSuvbsa`. (CS3D `packages/core/src/utilities/getScalingParameters.ts`, `scaleArray.ts`, `cache/classes/BaseStreamingImageVolume.ts`)
- Who fills `scalingModule`: in 5.x, instances registered through `@cornerstonejs/metadata` `addDicomWebInstance(imageId, json)` get it automatically from the default typed provider (`packages/metadata/src/utilities/metadataProvider/scalingFromInstance.ts`, calls `calculateSUVScalingFactors` per instance). The older pattern (still in demos and OHIF `extensions/default/src/init.ts`) computes factors for the whole series and registers a custom `scalingModule` provider. Prefer the whole-series call: calculate-suv validates that series-level fields are identical across instances and picks the earliest acquisition time.
- If required fields are missing the provider silently falls through → PET shows raw Bq/ml, not SUV. The component must detect this (`isPTPrescaledWithSUV` / `volume.scaling?.PT?.suvbw`) and label units accordingly.
- calculate-suv rules (`calculateSUVScalingFactors.ts`): `CorrectedImage` must contain `ATTN` and `DECY`; `Units` ∈ `BQML` | `CNTS` (Philips only, needs private SUVScaleFactor / ActivityConcentrationScaleFactor `7053,1000` / `7053,1009`) | `GML`; `PatientWeight` non-zero; decay time ≥ 0. SUVlbm/SUVbsa additionally need `PatientSize` (+ `PatientSex` for lbm). Start time = `RadiopharmaceuticalStartDateTime`, else `RadiopharmaceuticalStartTime` + `SeriesDate`. GE private post-injection time (`0009,100D`) supported by calculate-suv but not wired by the CS3D providers.

## 5. What the WADO-RS metadata endpoint must return

DICOM JSON (PS3.18 F.2), one object per instance, keyed by 8-hex tag. Consumer: `wadors` metadata provider (tags from `metaDataProvider.ts`) and `@cornerstonejs/metadata`.

| Purpose | Tags |
|---|---|
| imageId construction (demo/OHIF build `…/series/{0020000E}/instances/{00080018}/frames/N` from the metadata) | StudyInstanceUID 0020000D, SeriesInstanceUID 0020000E, SOPInstanceUID 00080018, SOPClassUID 00080016, NumberOfFrames 00280008 |
| Volume geometry | ImagePositionPatient 00200032, ImageOrientationPatient 00200037 (6 values), PixelSpacing 00280030, Rows 00280010, Columns 00280011, FrameOfReferenceUID 00200052, SliceThickness 00180050, SpacingBetweenSlices 00180088; enhanced multiframe: SharedFunctionalGroups 52009229 / PerFrameFunctionalGroups 52009230 (PlanePosition/PlaneOrientation/PixelMeasures) |
| Pixel decoding | SamplesPerPixel 00280002, PhotometricInterpretation 00280004, BitsAllocated 00280100, BitsStored 00280101, HighBit 00280102, PixelRepresentation 00280103, PlanarConfiguration 00280006, **transfer syntax: AvailableTransferSyntaxUID 00083002** (loader reads 00020010 or 00083002 — `getTransferSyntax`) |
| Modality LUT / VOI | RescaleIntercept 00281052, RescaleSlope 00281053, RescaleType 00281054, WindowCenter 00281050, WindowWidth 00281051, VOILUTFunction 00281056 |
| Series / fusion gating | Modality 00080060, SeriesDate 00080021, SeriesTime 00080031, AcquisitionDate 00080022, AcquisitionTime 00080032, SeriesNumber, InstanceNumber |
| PET SUV (PS3.3 C.8.9.1/C.8.9.2) | Units 00541001, CorrectedImage 00280051 (multi-value), DecayCorrection 00541102, RadiopharmaceuticalInformationSequence 00540016 → RadionuclideTotalDose 00181074, RadionuclideHalfLife 00181075, RadiopharmaceuticalStartTime 00181072, RadiopharmaceuticalStartDateTime 00181078; PatientWeight 00101030, PatientSize 00101020, PatientSex 00100040; FrameReferenceTime 00541300, ActualFrameDuration 00181242; Philips 70531000/70531009 when Units=CNTS |

Frames endpoint: the loader derives the transfer syntax from the **part** `Content-Type` of the multipart response (`extractMultipart` → `getTransferSyntaxForContentType`); with no `transfer-syntax=` parameter and `application/octet-stream` it assumes Implicit VR Little Endian (`loadImage.ts`). Request Accept is `multipart/related; type=application/octet-stream; transfer-syntax=*`.

## 6. Gaps in our current `wado.py` (local findings)

1. **UID mismatch → 404s.** The metadata endpoints `pydicom.dcmread` the stored file and return `ds.to_json_dict()`. Stored bytes keep the **original** UIDs (#115), while `DicomFile`/`DicomSeries`/`DicomStudy` rows and URL lookups use **HashUID pseudonyms**. Any client that builds frame URLs from returned Series/SOP UIDs (CS3D demo helper, OHIF) will request original UIDs and get 404. The endpoint must rewrite 0020000D/0020000E/00080018/00200052 (and nested references) to the pseudonyms before serialising.
2. **PHI leak.** Same endpoints return PatientName/ID/BirthDate etc. from the file; `DicomFile.metadata` is already PHI-stripped (`phi.PHI_TAG_KEYWORDS`) and pseudonymised, but is keyword-keyed, not DICOM JSON. Fix: apply the same strip + `helpers.dicom_uid.pseudonymize_uid` to the pydicom `Dataset` (recursively) and then `to_json_dict()`. PHI set deliberately keeps PatientWeight/Size/Sex — needed for SUV, keep it that way.
3. **No transfer syntax signalled.** `to_json_dict()` omits file meta (0002,0010) and nothing adds 00083002; frames parts are sent as `Content-Type: application/octet-stream` without `transfer-syntax`. Native (uncompressed) data works by luck; encapsulated (JPEG/J2K/RLE) CT/PET frames will be decoded as raw → garbage. Fix: add `transfer-syntax=<file TS UID>` to each frame part's Content-Type (and 00083002 to metadata). Also: explicit VR big-endian not handled.
4. Frames endpoint decodes the whole dataset per request (`ds.pixel_array[i]` for native multiframe; full `dcmread` always) — performance item for the "Performance" open question, not correctness.
5. `DicomFile.image_orientation_patient` is a 3-float column ("row direction cosines") — IOP is 6 values; don't serve geometry from DB columns, keep serving from the file.
6. No QIDO-RS; not needed — the viewer entry contract (map #175) supplies Study + Series UIDs.

## 7. Reference implementations

- **OHIF TMTV mode** (`modes/tmtv`, `extensions/tmtv`): exact PET/CT 3×3 layout (CT, PET, fusion rows + PET MIP) with Crosshairs per row, camera/VOI syncs, SUV panel, TMTV segmentation. `modeModalities: [['PT','CT']]` — **PT+CT only, not MR**; React + full OHIF app shell; heavy. Good as behavioural spec, not as a dependency.
- **OHIF MPR hanging protocol** (`extensions/cornerstone/src/hps/mpr.ts`) + **ViewportDataOverlayMenu** (`extensions/cornerstone/src/components/ViewportDataOverlaySettingMenu`) in the basic/longitudinal mode: generic "add foreground display set" fusion of any overlayable series (covers MR+PET).
- OHIF is a React SPA; our target is a Lit/Vite web component. Embedding OHIF means an iframe/separate app, its own data-source config and auth, and losing our component/annotation-storage contract.
- **CS3D examples** `crossHairs`, `petCt`, `stackToVolumeFusion`, `worldCrosshairSliceIntersectionsPetCt` are framework-free TS and map 1:1 onto a Lit component.

## Recommendation

- Build directly on `@cornerstonejs/core` + `tools` + `dicom-image-loader` (+ `@cornerstonejs/metadata`) inside the Lit component, porting the `crossHairs` and `petCt` examples; use OHIF TMTV only as behaviour reference. Don't embed OHIF.
- Layouts: `1×1` (one ORTHOGRAPHIC viewport, orientation switch) and `1×3` (ax/sag/cor + Crosshairs, one tool group). Fusion = same layouts with two volumes per viewport (CT/MR back, PET front with `hsv`/opacity slider/SUV 0–5 VOI); optional extra PET-only row needs a second tool group + camera syncs.
- Use legacy `ORTHOGRAPHIC` now (examples, OHIF use it); keep CS3D calls behind a small internal adapter since v5 flags migration to `PLANAR_NEXT`. Pin CS3D 5.10.x.
- Gate "volume/MPR capable" with OHIF's reconstructability rule; gate "fusable" with equal FrameOfReferenceUID (CS3D throws otherwise) — matches #175's "Open fused".
- Compute SUV per series with `calculateSUVScalingFactors`; show "SUVbw" only when scaling succeeded, else "Bq/ml"/raw units.
- Backend prerequisites (new tickets): metadata endpoint must (a) rewrite UIDs to pseudonyms, (b) strip PHI, (c) emit 00083002; frames endpoint must send `transfer-syntax=` per part. Without (a) the viewer cannot load any series at all.
