# Whole-slide DICOM (NDPI conversion output) in the app: storage, viewer, grouping

Findings only; the recommendations are input to a decision, not a locked decision. Date 2026-10-17.

Evidence tags: **[V]** verified (read in source or run on the real converted output), **[U]** unverified (inferred, or source not reachable).

Sources read:

- **[out]** Real converted set of `CMU-1.ndpi` (6 files) in the session scratchpad `bench/out`, read with pydicom 3 (`stop_before_pixels` / frame extract). Made by `convert_ndpi_to_dicom` (wsidicomizer 0.30).
- **[std]** DICOM PS3.3 C.8.12.4 (Whole Slide Microscopy Image module, Image Type flavors), C.8.12.2, C.8.12.3, C.8.12.5: https://dicom.nema.org/medical/dicom/current/output/chtml/part03/sect_C.8.12.4.html (and sibling sections). Fetched through a summarizing tool, not verbatim; Supplement 145 and PS3.4 not read.
- **[wsidicom]** `wsidicom/uid.py`, `series/series.py`, `wsidicom.py` as installed in `.venv` (`SlideUids`, `_validate_collection`).
- **[cs3d]** `@cornerstonejs/core` 5.10.11 `dist/esm/utilities/WSIUtilities.js` (`loadWSIData`), installed in `.dev-data/webcomponents/node_modules`.
- **[dmv]** `dicom-microscopy-viewer` 0.48.24 `src/metadata.js` (`groupColorInstances`), same install.
- **[repo]** `MiqaResearch/data/models/{dicom_file,dicom_series}.py`, `tasks/dicom_handling/{records,participant,frame_index}.py`, `extractors/pathology.py`, `interfaces/http/api/views/dicom/{metadata,frames}.py`, viewer code `.dev-data/webcomponents/src/viewer/{wsi.ts,series.ts,adapter/cornerstone/wsi.ts,annotations.ts}`, `GLOSSARY.md`.
- **[wsi-research]** Earlier note `docs/research/cornerstone3d-wsi-wado.md` on branch `research/cornerstone3d-wsi` (#186); also `research/ndpi-dicom-conversion` (#107) and `research/ndpi-dicom-tile-bytes`.

## What the converter produces [V][out]

One Study, **one Series**, six SOP Instances; all share StudyInstanceUID, SeriesInstanceUID and FrameOfReferenceUID (label and overview included). Modality `SM`, SOP class VL Whole Slide Microscopy (1.2.840.10008.5.1.4.1.1.77.1.6), JPEG Baseline, YBR_FULL_422, `TILED_FULL`, no per-frame functional groups, no Extended Offset Table, one optical path with an ICC profile.

| InstanceNumber | ImageType | TotalPixelMatrix (cols x rows) | Tile | Frames | PixelSpacing (mm) | Size |
|---|---|---|---|---|---|---|
| 2 | ORIGINAL\PRIMARY\VOLUME | 51200 x 38144 | 512 | 7500 | 0.000455 | 189 MB |
| 3 | DERIVED\PRIMARY\VOLUME\RESAMPLED | 12800 x 9536 | 512 | 475 | 0.00182 | 13 MB |
| 4 | DERIVED\PRIMARY\VOLUME\RESAMPLED | 3200 x 2384 | 512 | 35 | 0.00728 | 0.9 MB |
| 1 | DERIVED\PRIMARY\VOLUME\RESAMPLED | 800 x 596 | 512 | 4 | 0.0292 | 75 KB |
| 5 | ORIGINAL\PRIMARY\OVERVIEW | 1191 x 408 | 1191 x 408 | 1 | 0.0641 | 60 KB |
| 6 | ORIGINAL\PRIMARY\LABEL | 352 x 408 | 352 x 408 | 1 | 0.0641 | 26 KB |

Also observed [V][out]: PixelSpacing is in the Shared Functional Groups (not top level); `ImageOrientationSlide`, `TotalPixelMatrixOriginSequence` and `ImagedVolumeWidth/Height` present on every instance; `ContainerIdentifier` and `SpecimenIdentifier` are both the literal `Unknown`; `PatientID`, `PatientName`, `AccessionNumber` are **empty**; `BurnedInAnnotation` is `YES` only on LABEL; SOP/Series/Study UIDs are random under pydicom's root (`1.2.826.0.1.3680043.8.498`), new on every conversion. Instance numbers do not follow level order (the coarsest level is 1, base is 2).

The "thumbnail" level (instance 1) is a normal VOLUME level, not `THUMBNAIL` (matches [wsi-research] #107: opentile NDPI has no thumbnail).

## Q1. `DicomFile` or a separate whole-slide model?

**Recommendation: regular `DicomFile` rows, one per instance, under one `DicomSeries` per slide. No new model.**

- The DICOM data model already is this shape: one slide = one Series of SM instances; the six instances are SOP Instances of that series [V][out]. `GLOSSARY.md` defines Dicom File as "One DICOM instance ... the unit of storage and WADO retrieval" [V][repo].
- Everything downstream is keyed on `DicomFile`: frame index and ranged reads (`frame_index`, `transfer_syntax_uid`), `/metadata` and `/frames` with de-identification, UID pseudonymization (`sop_instance_uid` unique), blinding, audit, `DerivedObjectProvenance`, storage [V][repo]. A second model would duplicate all of it.
- Ingestion already handles it: `extractors/pathology.py` (#124) builds a per-instance `pathology_summary` with `image_type`, `frame_count`, `total_pixel_matrix_*`, tile size; pixel spacing is read from the functional groups; `frame_of_reference_uid` is stored per file and `DicomSeries.frame_of_reference_uid` resyncs to the shared value [V][repo]. For the 6 files this gives one series with FoR set [U: not run end-to-end, derived from [out] plus code].
- The per-level data lands correctly per file: `pixel_spacing` differs per level (good, it is per `DicomFile`); `DicomSeries.file_size_in_mb` sums all six [V][repo].
- Filtering by flavor does not need a column: `metadata` has a jsonb GIN index (`jsonb_path_ops`), so `metadata @> '{"pathology_summary":{"image_type":"LABEL"}}'` is indexable [V][repo model]. Add a column only if a hot query needs it [U].
- A `Slide` model is only justified later if slide-level fields (specimen, stain, container) must be queried across series. They are `Unknown` for this converter today [V][out], and derivable from `DicomSeries` plus the base file's `metadata` [U].

Gaps in ingestion of converter output (not model issues) [V][repo][out]:

1. **Empty PatientID**: `participant.match_or_create_participant` raises `ValueError` ("no usable patient identifier"), so all six files would be per-file errors. The pipeline that calls `convert_ndpi_to_dicom` must inject patient identity (wsidicomizer takes a metadata object) or the ingestion needs an override.
2. **New random UIDs per conversion**: converting the same NDPI twice yields a second study/series, not a duplicate-match. Dedup must happen on the NDPI (hash) before conversion, or conversion must be given stable UIDs [U: wsidicomizer option not checked].
3. Never ingest a partial set. Series-level aggregates tolerate it, but a viewer opened on a series missing the base level shows a blurry slide [U].

## Q2. Handling in the viewer (spec #271)

State today [V][repo]: the viewer already opens `SM` series. `isWholeSlide(series)` = any instance has the WSI SOP class; `createWsiView` builds a `MiresWSIViewport` (CS3D `WHOLE_SLIDE` wrapping dicom-microscopy-viewer) from `/series/{uid}/metadata` and fetches tiles from our `/frames/{n}`. A Playwright test seeds a synthetic TILED_FULL slide (`browser-tests/wsi.spec.ts`). The delivery gaps listed in [wsi-research] §4 (broken `/frames`, raw-header `/metadata` with raw UIDs and PHI, whole-file read per tile) are fixed on main: `/metadata` goes through `deidentify()` and pseudonymized UIDs, `/frames` uses the frame index [V][repo: views/dicom/metadata.py, frame_index.py].

How the six instances are treated by the libraries [V][cs3d][dmv]:

- `wsiImageIds(series)` passes **all** instances to `WSIViewport`. CS3D `loadWSIData` builds a `VLWholeSlideMicroscopyImage` for each but keeps only `ImageType[2]` = `VOLUME` or `THUMBNAIL` for display; dmv's channel grouping applies the same filter. So LABEL and OVERVIEW are loaded as metadata and **never drawn**. Pyramid assembly (sort by size, pick level by zoom) is done by dmv from the VOLUME instances; it needs no explicit level order from us.
- CS3D overwrites every instance's FrameOfReferenceUID with the first one's if they differ (`loadWSIData`), so a label with a different FoR would not break the pyramid.
- Cornerstone3D is not a pyramid-aware stack: it has no multi-resolution concept for WSI other than via dmv. The earlier note's maturity warnings stand (beta, `WHOLE_SLIDE_NEXT` migration, DPR bugs) [wsi-research §5; unverified now against upstream main].

Issues in the current viewer code for converter output [V][repo + out, impact U]:

1. **`series.images[0]` is not the base level.** `sortInstances` orders by InstanceNumber, and the converter numbers the 800-px level 1, the base 2. `annotations.ts` uses `series.images[0]` as the "slide's base level" referenced image and for the Frame of Reference (`referencedImageId ??= series.images[0].imageId`; README says "the slide's base level"). FoR is the same on all six, but the referenced image would be the coarsest level. Pick the VOLUME instance with the largest `TotalPixelMatrixColumns x Rows` instead. Whether the saved SR's reference matters to a consumer is unverified.
2. `tilesCacheSize` takes the largest `Rows x Columns` over all instances, which includes the single-frame label/overview (408 x 1191 = 486k px > 512 x 512 = 262k px), so the dmv cache shrinks from 512 to 276 tiles. Compute it over VOLUME/THUMBNAIL instances only.
3. **PHI**: LABEL and OVERVIEW are the images most likely to show the slide label. In `CMU-1` the OVERVIEW (flagged `BurnedInAnnotation=NO`) visibly contains the handwritten label text "CMU-1" (viewed the decoded frame) [V][out]. `contains_burned_in_annotations` is stored on `DicomFile` but nothing in the repo filters on it [V: grep]. Today `/frames` of label/overview is readable by anyone with `read`, even though no viewer draws them. Per the glossary, the De-identification Profile "does not touch pixel" data [V][GLOSSARY].
4. Fusion, MPR, SEG do not apply (WSI view has `imageCount: 1`, no invert/W-L) [V][repo wsi.ts, adapter]. Related Series / Fusion: a slide's FoR (slide coordinates) will not equal any radiology series' FoR, so the "same Frame of Reference" rule excludes it from fusion naturally [V][GLOSSARY]; whether the series list hides or labels slides as non-fusable is [U].

**Recommendation:** keep one Viewer Session = one slide series = one `WHOLE_SLIDE` viewport. Server side, serve only VOLUME/THUMBNAIL instances to the viewer by default (filter `/metadata` and `/frames` on `pathology_summary.image_type`), and gate LABEL/OVERVIEW behind the same raw-access permission as raw DICOM (ADR 0027) or drop them at conversion. Client side, fix items 1 and 2. If label/overview must be shown, add them as a separate, explicit "slide info" request (below), not through `WSIViewport`.

## Q3. How the app knows the files are one image, and how to show it

Grouping rule, in order of strength:

1. **SeriesInstanceUID** (same value on all six) [V][out]. The repo already groups on it: one `DicomSeries` per series UID (`unique` on `series_instance_uid`) [V][repo].
2. **FrameOfReferenceUID** shared by all instances, including label and overview [V][out]; `DicomSeries.frame_of_reference_uid` stores it [V][repo]. The standard says a Frame of Reference "typically only applies to a single mounting of a slide" and allows locating multiple images "within the Series of a single Frame of Reference" [V][std C.8.12.2 Note 1]. PS3.3 C.8.12.4 itself, as fetched, does **not** say that pyramid layers must share a Series or FoR [V][std]; wsidicom nevertheless defines "the UIDs that should be common for all files of a slide" as Study + Series + FoR (`SlideUids`) and rejects mismatches [V][wsidicom]. Treat series + FoR as de-facto rule, not a standard requirement.
3. Not usable as identity: `ContainerIdentifier` / `SpecimenIdentifier` are `Unknown` from this converter [V][out]. Useful only when the source provides real values [U].

Role of each instance (Image Type value 3, PS3.3 C.8.12.4 Table C.8.12.4-2 [V][std]):

| Flavor | Meaning | Use |
|---|---|---|
| VOLUME | regularly sampled layer, "may be used for each layer of a Multi-Resolution Pyramid"; shall not include the label | pyramid level |
| THUMBNAIL | may be the apex (lowest resolution) layer; no label | pyramid apex (none in CMU-1) |
| OVERVIEW | whole glass slide, "shall include at least part of the label" | slide metadata |
| LABEL | "the slide label only" | slide metadata |

`SpecimenLabelInImage` shall be YES for OVERVIEW/LABEL [V][std]; check this attribute in addition to the stored `BurnedInAnnotation` when deciding what is PHI [U: not checked in the output].

Within the pyramid: levels are told apart by `TotalPixelMatrixColumns/Rows` (and `PixelSpacing`), not by InstanceNumber or file size; levels need not be consecutive (CMU-1: pyramid indices 0/2/4/6, scale 1/4/16/64, no 1/3/5) [V][out][wsi-research #107]. `DimensionOrganizationType` decides frame lookup: `TILED_FULL` means frame number = f(tile row, col) with no per-frame positions; `TILED_SPARSE` (or absent) needs `PerFrameFunctionalGroupsSequence` / `PlanePositionSlideSequence` [V][wsi-research §2 from dmv `metadata.js`; PS3.3 C.8.12.4.1.2 names TILED_FULL only [V][std]]. The converter only emits TILED_FULL, so the frame index and viewer path need nothing special; other vendors' SPARSE files would [U].

**Frontend recommendation**

- **One row per slide in the series list**, the series being the unit: show description, modality `SM`, base size (from the base VOLUME instance: `51200 x 38144`), level count, not "6 files". Today file counts shown for a series would read 6 [U: list code not checked].
- **Open as one image**: the pyramid is a single WSI image with a zoom range; dmv builds it from the VOLUME levels.
- **Label and overview as slide metadata**, not as pyramid levels or series rows: the overview doubles as the minimap (dmv already draws its own overview map from the pyramid) and the label as an optional "slide info" panel, only if PHI policy allows (Q2 item 3). Neither should be selectable as separate series.
- **Slide-level fields for the UI** (width/height mm from `ImagedVolumeWidth/Height`, base spacing, objective power, level count) are already collected per file in `pathology_summary`/`pixel_spacing`; add `imaged_volume_*` if needed [V][repo for what exists; U for what's missing].

## Open points

- Run ingestion end-to-end on the six files (with an injected PatientID) to confirm one series, FoR on the series, six `DicomFile` rows, and the series list rendering [U].
- Read Supplement 145 / PS3.4 for a normative statement on pyramid-in-one-series [U]; PS3.3 C.8.12.4 as fetched is silent.
- Decide the PHI policy for LABEL/OVERVIEW pixels (drop at conversion vs. serve with a permission vs. blur) before any UI shows them. This is the only item with compliance impact.
