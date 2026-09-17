# DICOM RDSR / Radiotherapy IOD Structures

**Issue:** #106 (child of design-spec map issue #98, "DICOM ingestion pipeline")
**Date:** 2026-09-17
**Scope:** Against primary sources — NEMA DICOM PS3.3 "Information Object Definitions", PS3.16 "Content Mapping Resource", and pydicom's own source pinned to the exact version this repo uses (`pydicom==3.0.2`, per `src/MiqaResearch/uv.lock`) — determine how RDSR (X-Ray Radiation Dose SR) and the four core Radiotherapy IODs (RTSTRUCT, RTPLAN, RTDOSE, RTIMAGE) are structured, how pydicom idiomatically parses them, and which third-party libraries (if any) offer higher-level IOD-aware parsing beyond raw pydicom dataset traversal.

## Method / primary sources used

- **DICOM PS3.3** (NEMA `dicom.nema.org`, "current" edition, fetched 2026-09-17) — SR Document Content Module (`sect_C.17.3.html`), SR Document General/Series Modules (`sect_C.17.1.html`, `sect_C.17.2.html`), RT-specific composite modules (`sect_C.8.8.*.html`), and the composite IOD annexes and their module tables (`sect_A.17.html`–`sect_A.20.html`, `sect_A.35.8.html`).
- **DICOM PS3.16** (NEMA `dicom.nema.org`, "current" edition) — the Projection X-Ray Radiation Dose template family: `sect_XRayRadiationDoseSRIODTemplates.html` (TID 10001), and the individual TID pages `sect_TID_10002.html`, `sect_TID_10003.html`, `sect_TID_10003B.html`, `sect_TID_10004.html`, `sect_tid_10007.html`.
- **pydicom source at the exact commit tag `v3.0.2` resolves to**: tag `v3.0.2` is a lightweight tag pointing directly at commit `20aa4b73aef76bffb6fbc46a8827588dfa9bb89d` (author date 2026-03-19T21:37:06Z — consistent with the `uv.lock` upload timestamp of the `pydicom-3.0.2` sdist, 2026-03-19T21:46:20Z). All pydicom permalinks below use this commit SHA, not a branch name or "latest".
- **PyPI JSON API** (`pypi.org/pypi/<name>/json`) and **GitHub REST API** (`api.github.com`, via `gh api`) for rt-utils, dicompyler-core, highdicom, dicom-numpy, and to verify `pyplati` does not exist.
- Every claim below that could be fetched directly was fetched directly in this session; a couple of narrower DICOM sub-tables (noted inline) could not be fully retrieved through the automated fetch tool in the time available and are flagged as such rather than asserted from memory.

**Note on the standard edition:** `dicom.nema.org`'s "current" tree is a living/rolling edition (its HTML pages self-identify as "DICOM PS3.x 2026c" in fetched content). The IOD/module/tag structure referenced here (tag numbers, module names, TID row content-item codes) has been essentially stable for RDSR/RT since these templates and modules were first introduced (RDSR templates: DICOM Supplement 94, ~2007; RT modules: present since DICOM's original RT supplements in the late 1990s) and is not expected to differ materially between recent standard editions. Where the exact edition matters (e.g. newly-added "Enhanced X-Ray Radiation Dose SR" object), this is called out explicitly.

---

## 1. RDSR (X-Ray Radiation Dose Structured Report)

### 1.1 SR content tree shape (PS3.3 C.17.3 "SR Document Content Module")

An SR document's payload is a single root Content Item — a `CONTAINER`-valued item — that recursively owns the rest of the tree through **Content Sequence (0040,A730)**. Every content item (root or nested) is itself a `Dataset` (a Sequence Item) with this shape:

- **Value Type (0040,A040)**, VR `CS` — declares what kind of content item this is. Per PS3.3 C.17.3 (Table C.17.3-7), the enumerated values are: `CONTAINER`, `TEXT`, `NUM`, `CODE`, `DATE`, `TIME`, `DATETIME`, `UIDREF`, `PNAME`, `COMPOSITE`, `IMAGE`, `WAVEFORM`, `SCOORD`, `SCOORD3D`, `TCOORD`.
- **Concept Name Code Sequence (0040,A043)**, VR `SQ` — the "what is this node" triplet: a single-item sequence whose item carries the standard *Code Sequence Macro* attributes `Code Value` (0008,0100), `Coding Scheme Designator` (0008,0102), and `Code Meaning` (0008,0104) (plus optional `Coding Scheme Version` (0008,0103)). This is the code triplet consumers branch on (e.g. `(122130, DCM, "Dose Area Product")`).
- **Relationship Type (0040,A010)**, VR `CS` — how this item relates to its *parent* (`CONTAINS`, `HAS PROPERTIES`, `HAS OBS CONTEXT`, `HAS CONCEPT MOD`, `HAS ACQ CONTEXT`, `INFERRED FROM`, `SELECTED FROM`); this attribute is on the *child*, not stored on the container, and governs the nesting semantics seen in the TID tables below (e.g. rows tagged "HAS CONCEPT MOD" vs. "CONTAINS" in the fetched TID 10001/10002 tables).
- **Content Sequence (0040,A730)**, VR `SQ` — present on `CONTAINER` items (and some others); each item of this sequence is itself a content item Dataset with the same shape, giving the tree its recursion.
- For **NUM** value-type items specifically: **Measured Value Sequence (0040,A300)**, VR `SQ`, single item, containing **Numeric Value (0040,A30A)**, VR `DS`, VM `1-n`, and **Measurement Units Code Sequence (0040,08EA)**, VR `SQ`, whose item is again a Code Sequence Macro triplet (e.g. `(Gy.m2, UCUM, "Gy.m2")`).

All of the above tag→keyword mappings were verified directly against pydicom 3.0.2's own DICOM data dictionary (`src/pydicom/_dicom_dict.py` at commit `20aa4b73a`):

```
0x0040A040: ('CS', '1',   "Value Type",                  '', 'ValueType')
0x0040A043: ('SQ', '1',   "Concept Name Code Sequence",  '', 'ConceptNameCodeSequence')
0x0040A010: ('CS', '1',   "Relationship Type",            '', 'RelationshipType')
0x0040A730: ('SQ', '1',   "Content Sequence",              '', 'ContentSequence')
0x0040A300: ('SQ', '1',   "Measured Value Sequence",       '', 'MeasuredValueSequence')
0x0040A30A: ('DS', '1-n', "Numeric Value",                  '', 'NumericValue')
0x004008EA: ('SQ', '1',   "Measurement Units Code Sequence", '', 'MeasurementUnitsCodeSequence')
```

Two practical nuances this confirms for a consumer:
- `NumericValue`'s VR is `DS` (Decimal String) with **VM `1-n`** — pydicom decodes it as a `pydicom.valuerep.DSfloat` (or a `MultiValue` of them if VM > 1), not a plain Python `float`; code should call `float(item.MeasuredValueSequence[0].NumericValue)` rather than assume a bare float, and should be defensive about VM > 1 in principle even though every RDSR NUM item actually used in TID 10001/10002/10003/10004/10007 is single-valued in practice.
- `ConceptNameCodeSequence`, `MeasuredValueSequence`, and `MeasurementUnitsCodeSequence` are all `SQ` with VM `1` at the top level, so the idiomatic access is always `...Sequence[0]` — pydicom does not special-case single-item sequences.

### 1.2 The RDSR-specific IOD and its template family (PS3.16)

RDSR objects are commonly encoded as the **X-Ray Radiation Dose SR IOD**, PS3.3 Annex **A.35.8** (module table **A.35.8.3**, confirmed by direct fetch). Its module table contains only `SR Document Series` (C.17.1), `SR Document General` (C.17.2), `SR Document Content` (C.17.3), plus the usual Patient/Study/Equipment/SOP Common modules — **no Image Pixel module**, confirming RDSR carries no pixel data at all. (A newer **Enhanced X-Ray Radiation Dose SR IOD**, Annex A.35.22, and a corresponding TID 10001-successor template also exist in current standard editions for newer/expanded content; this research focuses on the classic X-Ray Radiation Dose SR IOD/TID 10001 family, which is what real-world CT/angio/fluoro equipment overwhelmingly emits today.) SOP Class UID `1.2.840.10008.5.1.4.1.1.88.67` ("X-Ray Radiation Dose SR Storage"), confirmed directly in pydicom's `_uid_dict.py` at v3.0.2 as `XRayRadiationDoseSRStorage`.

The content tree itself follows **PS3.16 TID 10001 "Projection X-Ray Radiation Dose"** (root container concept `(113701, DCM, "X-Ray Radiation Dose Report")`), which nests several sub-templates. Rows/content items confirmed by direct fetch of the live standard pages:

**TID 10001 (root, selected rows):**
| Row | Value Type | Concept name | Notes |
|---|---|---|---|
| 1 | CONTAINER | `(113701, DCM, "X-Ray Radiation Dose Report")` | root |
| 2 | CODE | `(121058, DCM, "Procedure reported")` | e.g. `(113704, DCM, "Projection X-Ray")` or `(71651007, SCT, "Mammography")` |
| 4 | CODE | `(122142, DCM, "Acquisition Device Type")` | |
| 6 | CODE | `(113705, DCM, "Scope of Accumulation")` | |
| 8–10 | CODE | `(113945/113943/113944, DCM, "X-Ray Detector/Source/Mechanical Data Available")` | Yes-No flags (CID 231) |
| 11–13 | INCLUDE | TID 10002 "Accumulated X-Ray Dose Data" (1-n, single/biplane) | |
| 14 | INCLUDE | TID 10003 "Irradiation Event X-Ray Data" (1-n instances) | one per irradiation event |
| 16 | IMAGE | `(121342, DCM, "Dose Image")` | optional dose-map image reference |
| 18 | CODE | `(113854, DCM, "Source of Dose Information")` | CID 10020 |

**Important correction vs. the issue's framing:** the issue text names "TID 10003 'CT Radiation Dose'" as a related template. That is **incorrect** — verified directly against the live standard: **TID 10003 is "Irradiation Event X-Ray Data"** (the per-event container included by TID 10001, table below). The actual **CT Radiation Dose** top-level template is **TID 10011** (root container reuses the same `(113701, DCM, "X-Ray Radiation Dose Report")` concept code, but the IE-level content is CT-specific via included templates **TID 10012** "CT Accumulated Dose Data" and **TID 10013** "CT Irradiation Event Data" — confirmed by direct fetch of `sect_CTRadiationDoseSRIODTemplates.html`). This doc otherwise stays scoped to the projection X-ray (TID 10001) family per the issue's primary ask; CT dose (TID 10011/10012/10013) is structurally parallel (same CONTAINER/NUM/CODE tree shape, same pydicom traversal approach) but uses different code values throughout and was not row-by-row verified here.

**TID 10002 "Accumulated X-Ray Dose Data"** (root `(113702, DCM, "Accumulated X-Ray Dose Data")`) is mostly calibration/geometry rows (Calibration Factor, Calibration Uncertainty, equipment landmark positions), and — relevant for dose totals — includes at Row 12 (`Req Type: MC`, conditional on integrated/fluoroscopy-guided/projection systems): **INCLUDE TID 10007 "Accumulated Total Projection Radiography Dose"**.

**TID 10007** rows (confirmed by direct fetch of `sect_tid_10007.html`) — this is where the aggregate/whole-procedure numbers a consumer typically wants live:
| Row | VT | Concept name | Units |
|---|---|---|---|
| 1 | NUM | `(113722, DCM, "Dose Area Product Total")` | Gy·m² |
| 2 | NUM | `(113725, DCM, "Dose (RP) Total")` | Gy |
| 3 | NUM | `(113737, DCM, "Distance Source to Reference Point")` | mm |
| 4 | NUM | `(113731, DCM, "Total Number of Radiographic Frames")` | 1 (dimensionless count) |
| 5–6 | CODE/TEXT | `(113780, DCM, "Reference Point Definition")` | |

**TID 10003 "Irradiation Event X-Ray Data"** (root `(113706, DCM, "Irradiation Event X-Ray Data")`) — the per-irradiation-event container, confirmed by direct fetch:
| Row | VT | Concept name | Notes |
|---|---|---|---|
| 3 | UIDREF | `(113769, DCM, "Irradiation Event UID")` | M |
| 6 | DATETIME | `(111526, DCM, "DateTime Started")` | M |
| 7 | CODE | `(113721, DCM, "Irradiation Event Type")` | CID 10002 |
| 8 | TEXT | `(125203, DCM, "Acquisition Protocol")` | U |
| 18 | NUM | `(122130, DCM, "Dose Area Product")` | Gy·m² |
| 21 | NUM | `(111636, DCM, "Entrance Exposure at RP")` | mGy |
| 27–29 | INCLUDE | TID 10003A/B/C "Irradiation Event X-Ray Detector/Source/Mechanical Data" | conditional sub-templates |

**TID 10003B "Irradiation Event X-Ray Source Data"** carries the exposure-technique numbers, confirmed by direct fetch:
| VT | Concept name | Units |
|---|---|---|
| NUM | `(113738, DCM, "Dose (RP)")` | Gy |
| NUM | `(113733, DCM, "KVP")` | kV |
| NUM | `(113824, DCM, "Exposure Time")` | ms |
| NUM | `(113734, DCM, "X-Ray Tube Current")` | mA |
| NUM | `(111631, DCM, "Average Glandular Dose")` | mGy (mammography) |
| NUM | `(113790, DCM, "Collimated Field Area")` | m² |
| NUM | `(113766, DCM, "Focal Spot Size")` | mm |
| NUM | `(113791, DCM, "Pulse Rate")` | pulse/s |
| NUM | `(113768, DCM, "Number of Pulses")` | 1 |
| CODE | `(111632, DCM, "Anode Target Material")` | |

These are the standard-defined code values a consumer should match on — none of the above were guessed; every code/scheme/meaning triplet was read directly off the live NEMA standard pages during this research session.

### 1.3 Idiomatic pydicom traversal

pydicom 3.0.2 exposes the content tree exactly as generic nested `Dataset`/`Sequence` objects — `dataset.ContentSequence` is a `pydicom.sequence.Sequence` of `Dataset` items, and each item's `SQ`-VR elements (including its own `ContentSequence`) are reachable the same way, recursively. There is no RDSR-specific object type; a walker looks like:

```python
def walk_sr(item, depth=0):
    concept = item.ConceptNameCodeSequence[0] if "ConceptNameCodeSequence" in item else None
    label = concept.CodeMeaning if concept is not None else "(root)"
    vtype = item.ValueType

    if vtype == "NUM":
        mv = item.MeasuredValueSequence[0]
        value = float(mv.NumericValue)
        units = mv.MeasurementUnitsCodeSequence[0].CodeMeaning
        print(f"{'  '*depth}{label} = {value} {units}")
    elif vtype == "CODE":
        code = item.ConceptCodeSequence[0]
        print(f"{'  '*depth}{label} = {code.CodeMeaning}")
    elif vtype == "TEXT":
        print(f"{'  '*depth}{label} = {item.TextValue}")
    else:
        print(f"{'  '*depth}{label} [{vtype}]")

    for child in item.get("ContentSequence", []):
        walk_sr(child, depth + 1)

walk_sr(dataset)  # dataset is the root SR Dataset itself, which has ContentSequence
```

This matches pydicom's own documented generic-traversal idiom, not an invented one: pydicom's bundled gallery example `examples/dicomtree.py` (fetched at the `v3.0.2` commit, `20aa4b73a`) builds a generic hierarchical tree viewer over *any* Dataset by iterating `for elem in ds`, checking `elem.VR == "SQ"`, and recursing into each sequence item's own Dataset — the exact same "check for a sequence-valued element and recurse" pattern, generalized. There is no SR-content-tree-specific convenience in that example (or anywhere else checked); it is pure generic-Dataset recursion, applied to the SR case by additionally branching on `ValueType`.

**Confirmed: pydicom 3.0.2 has no dedicated high-level SR content-tree API.** This was checked three ways against the pinned commit, not assumed from memory:
1. `src/pydicom/sr/` exists as a package, but its contents (`__init__.py`, `_cid_dict.py`, `_concepts_dict.py`, `_snomed_dict.py`, `codedict.py`, `coding.py`) are entirely about **code dictionaries and a `Code` NamedTuple** for representing/comparing coded concepts (context groups / CIDs, SNOMED↔SRT mapping) — not about walking or constructing a `ContentSequence` tree. `coding.py`'s `Code` class (fetched in full) is just `NamedTuple('Code', value, scheme_designator, meaning, scheme_version)` with equality logic for SNOMED/SRT code aliasing; it has no relationship to `ContentSequence`/`ValueType` traversal.
2. A GitHub code search scoped to `repo:pydicom/pydicom` for `ContentSequence` returns exactly 3 hits, none in a dedicated SR module (`src/pydicom/fileset.py`, `tests/test_util.py`, `tests/test_fileset.py` — all unrelated to SR trees, e.g. `fileset.py`'s hit is DICOMDIR-record content, not SR).
3. pydicom's documentation guide index (`doc/guides/`, fetched at the pinned commit) has no "structured report"/SR guide page — only `cli`, `decoding`, `element_value_types.rst`, `encoding`, `glossary.rst`, `plugin_table.rst`, `user/`.

`pydicom.dcmread()` on an RDSR file returns an ordinary `Dataset`; the SR-specific attributes (`ValueType`, `ContentSequence`, etc.) are populated exactly as any other tag, keyed by pydicom's standard dictionary (verified above), with no `PixelData`/`pixel_array` present (per the A.35.8.3 module table, RDSR has no Image Pixel module).

---

## 2. RTSTRUCT (RT Structure Set)

**IOD:** PS3.3 Annex **A.19** "RT Structure Set IOD"; module table **A.19.3**, fetched directly and confirmed to list **only** these RT-relevant modules: `RT Series` (C.8.8.1, M), `Structure Set` (C.8.8.5, M), `ROI Contour` (C.8.8.6, M), `RT ROI Observations` (C.8.8.8, M), `Approval` (C.8.8.16, U) — with the usual Patient/Study/Equipment/SOP Common modules, and (Note 2-gated) `Frame of Reference` (U). **No Image Pixel module anywhere in the table** — confirms RTSTRUCT carries no pixel data of its own; it is pure geometry that references a separate image series. SOP Class UID `1.2.840.10008.5.1.4.1.1.481.3` ("RT Structure Set Storage"), confirmed in pydicom's `_uid_dict.py`.

**How it references the annotated images** — **Structure Set Module (C.8.8.5)**:
- `ReferencedFrameOfReferenceSequence` (3006,0010) → item has `FrameOfReferenceUID` (0020,0052) and `RTReferencedStudySequence` (3006,0012) → item has `RTReferencedSeriesSequence` (3006,0014) → item has `SeriesInstanceUID` (0020,000E) and **`ContourImageSequence`** (3006,0016), whose items each carry `ReferencedSOPClassUID` (0008,1150)/`ReferencedSOPInstanceUID` (0008,1155) pointing at one specific slice (a CT/MR instance) of the parent series.
- **`StructureSetROISequence`** (3006,0020): one item per ROI, with `ROINumber` (3006,0022), `ReferencedFrameOfReferenceUID` (3006,0024), `ROIName` (3006,0026), `ROIDescription` (3006,0028), `ROIVolume` (3006,002C, computed volume if present), `ROIGenerationAlgorithm` (3006,0036).

**How the contour geometry itself is stored** — **ROI Contour Module (C.8.8.6)**:
- **`ROIContourSequence`** (3006,0039): one item per ROI (linked back to `StructureSetROISequence` by `ReferencedROINumber` (3006,0084)), each with `ROIDisplayColor` (3006,002A) and a **`ContourSequence`** (3006,0040) — one item per 2D contour (typically one per slice), each with:
  - `ContourGeometricType` (3006,0042) — enumerated `POINT`, `OPEN_PLANAR`, `OPEN_NONPLANAR`, `CLOSED_PLANAR`, `CLOSEDPLANAR_XOR`,
  - `NumberOfContourPoints` (3006,0046),
  - **`ContourData`** (3006,0050) — the flat list of (x,y,z) triplets, VR `DS`, VM `3-3n` (so `len(ContourData) == 3 * NumberOfContourPoints`),
  - its own back-reference **`ContourImageSequence`** (3006,0016) pointing at the exact slice SOP Instance this specific contour belongs to (this is per-contour, distinct from the series-level `ContourImageSequence` under `RTReferencedSeriesSequence`).

**RT ROI Observations Module (C.8.8.8)** — the clinical-interpretation layer, one item per ROI in `RTROIObservationsSequence` (3006,0080): `ObservationNumber` (3006,0082), `ReferencedROINumber` (3006,0084, links to the same ROI), `RTROIInterpretedType` (3006,00A4, e.g. `ORGAN`, `PTV`, `EXTERNAL`), `ROIInterpreter` (3006,00A6).

Practical shape with `pydicom.dcmread()`: a `Dataset` with no `PixelData`; nesting depth reaches 4–5 levels for the reference chain (`ReferencedFrameOfReferenceSequence → RTReferencedStudySequence → RTReferencedSeriesSequence → ContourImageSequence`) and 3 levels for geometry (`ROIContourSequence → ContourSequence → ContourData`), each `SQ` level typically 1-n items (one item per study/series/slice/ROI as appropriate).

---

## 3. RTPLAN, RTDOSE, RTIMAGE and their cross-references

Module tables for all three were fetched directly (PS3.3 **A.20.3** RT Plan, **A.18.3** RT Dose, **A.17.3** RT Image); the Image-Pixel-module presence/absence differs meaningfully between them and is the key structural signal for what `pydicom.dcmread()` returns:

| IOD | Annex | Image Pixel module | Multi-frame module | Key RT module |
|---|---|---|---|---|
| RT Plan | A.20 | **absent entirely** | — | RT General Plan (C.8.8.9, M), RT Beams (C.8.8.14, C) |
| RT Dose | A.18 | **Conditional** — "Required if dose data contains grid-based doses" | Conditional, same condition | RT Dose (C.8.8.3, M) |
| RT Image | A.17 | **Mandatory** | Conditional | RT Image (C.8.8.2, M) |

### RTPLAN

**IOD A.20**, SOP Class `1.2.840.10008.5.1.4.1.1.481.5` (`RTPlanStorage`, confirmed in pydicom's `_uid_dict.py`). **RT General Plan Module (C.8.8.9)**: `RTPlanLabel` (300A,0002, Type 1), `RTPlanName` (300A,0003, Type 3), `RTPlanGeometry` (300A,000C, Type 1 — whether the plan is based on patient or device geometry), and **`ReferencedStructureSetSequence`** (300C,0060, Type 1C) — the SOP Instance Reference Macro (`ReferencedSOPClassUID`/`ReferencedSOPInstanceUID`) pointing at the parent RTSTRUCT this plan is based on. Beam/fraction data lives in separate conditional modules: **RT Fraction Scheme (C.8.8.13)** and **RT Beams (C.8.8.14)** — the latter carries `BeamSequence` (300A,00B0), each item having `BeamNumber`, `BeamName`, and a `ControlPointSequence` (300A,0111) of per-control-point geometry (`GantryAngle` (300A,011E), `SourceToSurfaceDistance` (300A,0130), etc.). No Image Pixel module at all — RTPLAN is pure geometry/dosimetry parameters, never pixel data.

### RTDOSE

**IOD A.18**, SOP Class `1.2.840.10008.5.1.4.1.1.481.2` (`RTDoseStorage`). **RT Dose Module (C.8.8.3)**: `DoseUnits` (3004,0002, e.g. `GY` or `RELATIVE`), `DoseType` (3004,0004), `DoseSummationType` (3004,000A, e.g. `PLAN`, `BEAM`, `FRACTION`, `BRACHY`, `CONTROL_POINT`), **`ReferencedRTPlanSequence`** (300C,0002) → SOP Instance Reference Macro pointing at the parent RTPLAN, `GridFrameOffsetVector` (3004,000C, the z-offsets of each dose plane for a 3D grid), and **`DoseGridScaling`** (3004,000E) — the float multiplier applied to raw `PixelData` integer values to get dose in `DoseUnits` (i.e. `dose = pixel_array * DoseGridScaling`). Unlike RDSR/RTSTRUCT, RTDOSE **does carry `PixelData`** — but only conditionally, per the A.18.3 module table ("Required if dose data contains grid-based doses"; a pure DVH-only or reference-point-only dose object could in principle omit it, though grid-based dose is the overwhelmingly common case in practice). When present, `pydicom.dcmread(...).pixel_array` returns the raw dose grid (typically 3D: frames × rows × columns for a `Multi-frame`-module dataset), which the consumer must multiply by `DoseGridScaling` to get physical dose.

### RTIMAGE

**IOD A.17**, SOP Class `1.2.840.10008.5.1.4.1.1.481.1` (`RTImageStorage`; an `EnhancedRTImageStorage` variant, `...481.23`, also exists per pydicom's UID dict but was not separately researched here). **RT Image Module (C.8.8.2)**: `RTImageLabel` (3002,0002), `RTImagePlane` (3002,000C), `RTImagePosition` (3002,0012), `RadiationMachineName` (3002,0020), `GantryAngle` (300A,011E), `RadiationMachineSAD` (3002,0022), **`ReferencedRTPlanSequence`** (300C,0002) and **`ReferencedBeamNumber`** (300C,0006) — together identifying which specific beam of which RTPLAN this portal/verification image corresponds to — plus `ExposureSequence` (3002,0030) for per-exposure imaging parameters. The **Image Pixel module is Mandatory** for RTIMAGE (confirmed directly in the A.17.3 table, annotated "appropriate for RT Images as projection images") — `pixel_array` is always populated, a single 2D projection image (portal image) unless the `Multi-frame` module is also present (conditional).

### Practical `dcmread()` shape summary

- **RTPLAN**: no `PixelData`/`pixel_array`; deep nesting under `BeamSequence[i].ControlPointSequence[j]` (confirmed against pydicom's own bundled gallery example, see §1.3 — `examples/input_output/plot_read_rtplan.py`, fetched at commit `20aa4b73a`, reads `ds.BeamSequence`, `beam.ControlPointSequence[0]`, `cp0.GantryAngle`, `cp0.SourceToSurfaceDistance`, confirming this is pydicom's own idiomatic access pattern, not invented here).
- **RTDOSE**: `PixelData`/`pixel_array` present when grid-based; must be combined with `DoseGridScaling`; `ReferencedRTPlanSequence` is the single top-level cross-reference to RTPLAN.
- **RTIMAGE**: `PixelData`/`pixel_array` always present (single 2D image, mandatory Image Pixel module); cross-references RTPLAN + a specific beam via `ReferencedRTPlanSequence`/`ReferencedBeamNumber`.

---

## 4. Third-party Python libraries beyond raw pydicom traversal

All four names below were checked by fetching their actual PyPI JSON metadata and/or GitHub API data in this session (not from memory).

- **`rt-utils`** (PyPI, [pypi.org/project/rt-utils](https://pypi.org/project/rt-utils/); GitHub `qurit/rt-utils`). PyPI summary: "A small library for handling masks and RT-Structs"; README (fetched) confirms it is "a minimal Python library for RT Struct manipulation" — its core is an `RTStructBuilder` for creating/loading RTSTRUCT files and converting between 3D boolean numpy masks and `ROIContourSequence` contour geometry (and back), i.e. it is specifically an RTSTRUCT↔mask conversion tool, not a general RT-IOD parser (it does not touch RTPLAN/RTDOSE/RTIMAGE). Depends on `pydicom`, `numpy`, `opencv-python`. **Maintenance:** latest PyPI release **1.2.7, uploaded 2023-01-08**; the GitHub repo itself is not archived and shows commits pushed as recently as **2026-08-15**, 256 stars, 64 open issues — i.e. actively developed on GitHub but with no new PyPI release in roughly three years at time of writing, so `pip install rt-utils` gets a build that is meaningfully behind `main`.
- **`dicompyler-core`** (PyPI, package name on PyPI is `dicompyler-core`, importable as `dicompylercore`; GitHub `dicompyler/dicompyler-core`). PyPI summary: "A library of core radiation therapy modules for DICOM / DICOM RT used by dicompyler". README (fetched) confirms its `dicompylercore` package ships a `dicomparser` module ("parse DICOM objects in an easy-to-use manner") plus `dvh` (Pythonic dose-volume-histogram access), `dvhcalc` (independent DVH calculation from RT Dose + RT Structure Set), and `dose` (dose data access including dose summation) — i.e. it does understand RTSTRUCT/RTDOSE (and, via the wider dicompyler ecosystem, RTPLAN/RTIMAGE) well enough to compute clinically-relevant quantities like DVHs, not just expose raw tags. Declared dependency is `pydicom>=2.4.0` (so it is written against the pydicom 2.x API surface but is not pinned away from 3.x). **Maintenance:** latest PyPI release **0.5.6, uploaded 2023-05-08**; GitHub repo not archived, last push **2026-07-20**, 161 stars, 30 open issues — similar pattern to rt-utils (repo alive, PyPI release cadence stalled since 2023).
- **`pyplati`** — **does not exist as a real, findable project.** Checked directly: `pypi.org/pypi/pyplati/json` returns HTTP 404, and `pypi.org/simple/pyplati/` also returns 404 (no such PyPI package, current or historical). A GitHub repository search for `pyplati` returns exactly one unrelated hit (`Bheeshma1992/PypLatin`, a Latin-language-learning project, unrelated to DICOM). No corroborating result was found anywhere. This should be treated as **not a real option** — whoever referenced it in the parent issue likely meant something else, or it was invented/misremembered; it is not being used as a source of any fact in this document.
- **`highdicom`** (PyPI, [pypi.org/project/highdicom](https://pypi.org/project/highdicom/); GitHub `ImagingDataCommons/highdicom`) — a real, actively maintained (last push **2026-09-15**, i.e. days before this research) library described in its own README (fetched) as "a pure Python package built on top of pydicom to provide a higher-level API," explicitly covering **reading and constructing Structured Report documents** (numerical results, qualitative evaluations, vector graphics) among other derived-object types (segmentations, parametric maps, key object selection, etc.). It is **not** described as handling RT Structure Set / RT Dose / RT Plan / RT Image objects — its RT-adjacent focus is segmentation/annotation objects, not the classic RT-therapy IOD family. Relevant as a candidate for higher-level, spec-aware SR construction/parsing (an alternative to hand-rolling the §1.3 tree walker) if the ingestion pipeline needs to *write* or richly validate SR content, not for RTSTRUCT/RTDOSE/RTPLAN/RTIMAGE.
- **`dicom-numpy`** (PyPI, GitHub `innolitics/dicom-numpy`) — noted only for completeness; PyPI summary "Extract image data into a 3D numpy array from a set of DICOM files." This is a generic multi-slice-image-to-3D-array combiner (spacing/orientation-aware stacking), unrelated to SR or RT-specific structures; it would only be relevant if the pipeline needs to reconstruct a 3D volume from the CT/MR series that an RTSTRUCT/RDSR references, not for parsing the RT/SR objects themselves.

---

## Summary / verdict for design-spec purposes

- **RDSR** is a pure `CONTAINER`/`NUM`/`CODE`/... tree (PS3.3 C.17.3) with no pixel data (confirmed via the A.35.8.3 module table). pydicom 3.0.2 has **no dedicated SR-tree API** — confirmed three independent ways against the pinned `v3.0.2` commit (`src/pydicom/sr/` is code-dictionary-only; a repo code search for `ContentSequence` returns 3 unrelated hits; no SR guide page exists in `doc/guides/`). A pipeline needs to hand-write a recursive walker keyed on `ValueType`/`ConceptNameCodeSequence[0].CodeValue`, exactly the generic-recursion pattern pydicom's own bundled `examples/dicomtree.py` demonstrates for arbitrary datasets. The standard-defined code values worth hard-coding as extraction targets (TID 10001/10002/10003/10003B/10007, all verified against the live standard) include Dose Area Product `(122130/113722, DCM)`, Dose (RP) `(113738/113725, DCM)`, Entrance Exposure at RP `(111636, DCM)`, KVP `(113733, DCM)`, Exposure Time `(113824, DCM)`, Total Number of Radiographic Frames `(113731, DCM)`, and Irradiation Event UID `(113769, DCM)` as the per-event join key.
- **Correction to the issue's premise:** TID 10003 is **not** "CT Radiation Dose" (it is "Irradiation Event X-Ray Data", the per-event container inside TID 10001). CT Radiation Dose is **TID 10011** (with TID 10012/10013 as its accumulated/per-event sub-templates). Any downstream design doc referencing "TID 10003 = CT Radiation Dose" should be corrected.
- **RTSTRUCT** has no pixel data (confirmed: A.19.3 module table has no Image Pixel module) and is purely a reference/geometry object: `ReferencedFrameOfReferenceSequence → RTReferencedStudySequence → RTReferencedSeriesSequence → ContourImageSequence` for "which slices does this apply to," and `StructureSetROISequence` + `ROIContourSequence → ContourSequence → ContourData` for "what are the ROI shapes." Both trees join on `ROINumber`/`ReferencedROINumber`.
- **RTPLAN/RTDOSE/RTIMAGE differ sharply in whether they carry pixel data**, and this is a structurally load-bearing fact for a pipeline design (confirmed directly from the A.20.3/A.18.3/A.17.3 module tables): RTPLAN never has pixel data (pure beam/fraction/geometry parameters, cross-referencing RTSTRUCT via `ReferencedStructureSetSequence`); RTDOSE conditionally carries a `PixelData` grid that must be scaled by `DoseGridScaling` and cross-references RTPLAN via `ReferencedRTPlanSequence`; RTIMAGE always carries `PixelData` (a single 2D projection/portal image) and cross-references a specific RTPLAN beam via `ReferencedRTPlanSequence`/`ReferencedBeamNumber`. A generic "does this RT object have pixel data" check on `dcmread()` output should branch on Modality/SOPClassUID rather than assume presence.
- **For library selection**: raw pydicom traversal (per the walker pattern in §1.3, and the module/tag paths in §2–3) is sufficient and is what this ingestion pipeline will most likely need to hand-roll for RDSR and the reference/geometry parts of RTSTRUCT/RTPLAN/RTDOSE/RTIMAGE, since none of the checked third-party libraries provide a single unified "parse any RT/SR IOD" API. If the pipeline specifically needs RTSTRUCT mask↔contour conversion, `rt-utils` is the closest real, working fit (but pinned PyPI release is ~3 years stale versus its GitHub `main`; consider installing from a git ref if features from `main` are needed). If it needs DVH computation or a slightly higher-level `dicomparser`-style read of RTSTRUCT/RTDOSE, `dicompyler-core` fits (same stale-PyPI caveat). If it needs to *construct* or richly validate SR content (as opposed to just reading it), `highdicom` is a real, currently-maintained option, though it does not cover the RT-therapy IOD family. `pyplati` is not a real project and should be dropped from consideration entirely.

## Citations (permalinks)

**DICOM PS3.3** (`https://dicom.nema.org/medical/dicom/current/output/chtml/part03/`):
- `sect_C.17.1.html`, `sect_C.17.2.html`, `sect_C.17.3.html` — SR Document Series/General/Content Modules
- `sect_C.8.8.1.html` (RT Series), `sect_C.8.8.2.html` (RT Image), `sect_C.8.8.3.html` (RT Dose), `sect_C.8.8.5.html` (Structure Set), `sect_C.8.8.6.html` (ROI Contour), `sect_C.8.8.8.html` (RT ROI Observations), `sect_C.8.8.9.html` (RT General Plan), `sect_C.8.8.14.html` (RT Beams)
- `sect_A.17.html` + `sect_A.17.3.html` (RT Image IOD + module table), `sect_A.18.html` + `sect_A.18.3.html` (RT Dose IOD + module table), `sect_A.19.html` + `sect_A.19.3.html` (RT Structure Set IOD + module table), `sect_A.20.html` + `sect_A.20.3.html` (RT Plan IOD + module table), `sect_A.35.8.html` + `sect_A.35.8.3.html` (X-Ray Radiation Dose SR IOD + module table)

**DICOM PS3.16** (`https://dicom.nema.org/medical/dicom/current/output/chtml/part16/`):
- `sect_XRayRadiationDoseSRIODTemplates.html` (TID 10001, TID 10002 root rows), `sect_TID_10002.html`, `sect_TID_10003.html`, `sect_TID_10003B.html`, `sect_TID_10004.html`, `sect_tid_10007.html`, `sect_CTRadiationDoseSRIODTemplates.html` (TID 10011/10012/10013 confirmation)

**pydicom** (pinned to tag `v3.0.2` → commit `20aa4b73aef76bffb6fbc46a8827588dfa9bb89d`):
- `https://github.com/pydicom/pydicom/blob/20aa4b73aef76bffb6fbc46a8827588dfa9bb89d/src/pydicom/_dicom_dict.py` (tag→keyword dictionary entries quoted in §1.1)
- `https://github.com/pydicom/pydicom/blob/20aa4b73aef76bffb6fbc46a8827588dfa9bb89d/src/pydicom/_uid_dict.py` (SOP Class UIDs quoted in §1.2/§3)
- `https://github.com/pydicom/pydicom/blob/20aa4b73aef76bffb6fbc46a8827588dfa9bb89d/src/pydicom/sr/coding.py` (full `Code` NamedTuple, quoted in §1.3)
- `https://github.com/pydicom/pydicom/tree/20aa4b73aef76bffb6fbc46a8827588dfa9bb89d/src/pydicom/sr` (directory listing: `_cid_dict.py`, `_concepts_dict.py`, `_snomed_dict.py`, `codedict.py`, `coding.py` — no tree-walking module)
- `https://github.com/pydicom/pydicom/blob/20aa4b73aef76bffb6fbc46a8827588dfa9bb89d/examples/dicomtree.py` (generic recursive Dataset/Sequence tree-walker, quoted in §1.3)
- `https://github.com/pydicom/pydicom/blob/20aa4b73aef76bffb6fbc46a8827588dfa9bb89d/examples/input_output/plot_read_rtplan.py` (RTPLAN `BeamSequence`/`ControlPointSequence` access idiom, quoted in §3)
- `https://github.com/pydicom/pydicom/tree/20aa4b73aef76bffb6fbc46a8827588dfa9bb89d/doc/guides` (guide index — no SR-specific guide page)
- GitHub code search `ContentSequence repo:pydicom/pydicom` → 3 results, none an SR-tree API (`src/pydicom/fileset.py`, `tests/test_util.py`, `tests/test_fileset.py`)
- `src/MiqaResearch/uv.lock` — confirms `pydicom==3.0.2` is the version this repo actually installs, with sdist upload time 2026-03-19T21:46:20Z (consistent with the `v3.0.2` tag's commit date above)

**Third-party libraries:**
- `https://pypi.org/pypi/rt-utils/json`, `https://raw.githubusercontent.com/qurit/rt-utils/master/README.md`, `https://api.github.com/repos/qurit/rtutils` (repo activity: `archived: false`, `pushed_at: 2026-08-15T00:03:40Z`, 256 stars, 64 open issues; latest PyPI release `1.2.7` uploaded `2023-01-08T00:59:05`)
- `https://pypi.org/pypi/dicompyler-core/json`, `https://raw.githubusercontent.com/dicompyler/dicompyler-core/master/README.rst`, `https://api.github.com/repos/dicompyler/dicompyler-core` (repo activity: `archived: false`, `pushed_at: 2026-07-20T04:29:12Z`, 161 stars, 30 open issues; latest PyPI release `0.5.6` uploaded `2023-05-08T16:20:38`)
- `https://pypi.org/pypi/pyplati/json` → HTTP 404; `https://pypi.org/simple/pyplati/` → HTTP 404; GitHub repository search for `pyplati` → 1 unrelated hit (`Bheeshma1992/PypLatin`)
- `https://pypi.org/pypi/highdicom/json`, `https://raw.githubusercontent.com/ImagingDataCommons/highdicom/master/README.md`, `https://api.github.com/repos/ImagingDataCommons/highdicom` (`archived: false`, `pushed_at: 2026-09-15T00:55:09Z`)
- `https://pypi.org/pypi/dicom-numpy/json`

## Notes on gaps / things not fully verified in the time available

- The full row-by-row content of TID 10003A ("Irradiation Event X-Ray Detector Data") and TID 10003C ("Irradiation Event X-Ray Mechanical Data") — e.g. exact codes for Distance Source to Detector / Distance Source to Entrance Surface / Positioner Primary Angle, which the issue asked about — were **not** retrieved from the live standard in this session (the fetch tool returned only TID 10003B content on the relevant queries); these exist as real DICOM content items but their exact code values should be re-verified against `sect_TID_10003A.html`/`sect_TID_10003C.html` before being hard-coded in an implementation.
- TID 10011/10012/10013 (CT Radiation Dose family) were confirmed to exist and to be structurally parallel to the projection-X-ray family, but were not verified row-by-row the way TID 10001–10007 were; treat their exact code values as unconfirmed until fetched directly.
- The DICOM standard edition fetched throughout is `dicom.nema.org`'s rolling "current" tree; this document does not pin to a specific dated/lettered edition (e.g. "2024e") the way the pydicom citations pin to an exact commit SHA, because the standard site does not expose the same kind of stable historical permalink pydicom's git history does. If bit-for-bit reproducibility against a frozen standard text is required later, re-fetch against an explicitly dated NEMA archive edition (e.g. `dicom.nema.org/medical/dicom/2024e/...`, which was seen to exist in search results during this research) rather than the "current" alias.
