# Research: deterministic UIDs + injected metadata in NDPI -> DICOM conversion

Resolves #304 (parent map #303). Findings only; no spec decisions locked.

Legend: **[V]** = verified this session, by reading installed source and/or running a conversion. **[U]** = unverified / inferred.
Env: wsidicomizer 0.30.0, wsidicom 0.35.0, pydicom 3.0.2, py3.14 (`.venv` site-packages; `pyproject.toml` pins only `wsidicomizer>=0.30.0`). Sample: CMU-1.ndpi (198 MB), converted with `include_levels=[-1,-2]` for speed (UID logic is level-independent).

## Answer
- **Yes** to both. UIDs can be fully deterministic, and PatientID / ContainerIdentifier / SpecimenIdentifier / Study+Series fields can be injected. [V]
- UIDs are stable across runs for identical inputs. File **bytes are not**, by default (timestamps) -> ingestion reports `duplicate_conflict`, not `skipped_duplicate`. Fixable (below). [V]

## API (wsidicomizer 0.30 / wsidicom 0.35)
- `WsiDicomizer.convert(..., metadata=WsiMetadata, default_metadata=WsiMetadata, uid_generator=Callable[[], UID] | UidGenerator, metadata_pre_processor=, metadata_post_processor=)` [V] (`wsidicomizer/wsidicomizer.py:150-181`).
- `metadata` overrides what is read from the file; `default_metadata` only fills gaps (merge order user > file > default) [V] (`wsidicomizer/metadata.py` `_select_value`). Build with `wsidicomizer.metadata.WsiDicomizerMetadata(study=, series=, patient=, slide=, ...)`; all args optional [V].
- A bare callable is wrapped in `CallableUidGenerator` (same zero-arg callable for every role) -> cannot be content-derived per role (only order-dependent counters). Use a `UidGenerator` subclass [V] (`wsidicom/metadata/uid_generator.py`).
- `UidGenerator` ABC, abstract methods, all must be implemented [V]:
  `study_uid(Study)`, `series_uid(Series)`, `frame_of_reference_uid(WsiMetadata)`, `dimension_organization_uid(WsiMetadata)`, `sample_uid(SlideSample)`, `pyramid_uid(Pyramid)`, `sop_uid(Dataset)`, `concatenation_uid(Dataset)`, `concatenation_source_uid(Dataset)`, `annotation_group_uid()`.
- Metadata-level UIDs are filled once by `MetadataUidResolver` (order: study, series, samples, pyramid, frame_of_reference, dimension_organization), inside a `@cached_property metadata`, so one value per conversion [V] (`dicomizer_source.py:237-251`, `uid_resolver.py`). **Any UID already set on the metadata is preserved verbatim and the generator is not called for it** [V; also confirmed by run: explicit Study/Series/FoR/Sample UIDs landed in output unchanged].
- `sop_uid(dataset)` is called per written instance (volume levels, label, overview, thumbnail), with the already-built `Dataset`, **before** `InstanceNumber` is set [V] (`wsidicom/file/file_writer.py:154,1653`). Output filename = `<SOPInstanceUID>.dcm`, so filenames become deterministic too [V].
- Useful `sop_uid` key inputs available on the dataset at call time: `SeriesInstanceUID`, `ImageType` (VOLUME/LABEL/OVERVIEW/THUMBNAIL), `TotalPixelMatrixColumns/Rows`, `NumberOfFrames` [V]. Label/overview/thumbnail have no `TotalPixelMatrix*` fallbacks verified beyond label/overview in the run [V]; **ImageType must be in the key** or label/overview/levels could collide [V logic].
- Metadata injection fields [V] (`wsidicom/metadata/*.py`, schema `dicom/*.py`):
  - `Patient(identifier=)` -> PatientID; `name` -> PatientName; also birth_date, sex, ... No issuer-of-patient-ID field in the model [V; absence only checked in `patient.py`].
  - `Study(uid, identifier=StudyID, accession_number, date, time, description, ...)`.
  - `Series(uid, number, description, body_part_examined)`.
  - `Slide(identifier: str | SpecimenIdentifier)` -> ContainerIdentifier (+ IssuerOfTheContainerIdentifierSequence if `SpecimenIdentifier` has an issuer).
  - `Slide(samples=[SlideSample(identifier=, uid=)])` -> SpecimenDescriptionSequence SpecimenIdentifier/SpecimenUID. If no sample is given, wsidicomizer inserts `SlideSample("Unknown")`, so **SpecimenIdentifier is "Unknown" unless set** [V] (`dicomizer_source.py:276-293`; seen in output).
  - `frame_of_reference_uid`, `dimension_organization_uids`, `pyramid.uid` (PyramidUID, volume instances only).
- Confidentiality: `include_confidential=False` drops patient name/id, label text/barcode, study, series, slide, FoR from the **file-derived** metadata before user metadata is merged, so injected values still apply [V] (`remove_confidential`, `merge` order). NDPI itself supplies no patient/study metadata in the sample (output had none until injected) [V for CMU-1; U for other scanners].

## Experiments (all [V])
1. `UidGenerator` subclass deriving all UIDs from `sha256(key|role|...)` (key = fixed string; in practice the NDPI sha256), plus injected Patient/Study/Series/Slide. Two conversions, 7s apart: **identical StudyInstanceUID, SeriesInstanceUID, FoR, PyramidUID, DimensionOrganizationUID, SpecimenUID, SOPInstanceUIDs, filenames, PatientID, ContainerIdentifier, StudyID**.
2. Same two runs: **file sha256 differed for every file**. Causes: (a) `InstanceCreationDate/Time` unconditionally overwritten with `datetime.now()` at write (`wsidicom/file/io/wsidicom_writer.py:336`, `wsidicom_io.py:337-341`; no parameter/hook); (b) `ContributingEquipmentSequence[].ContributionDateTime = datetime.now()` added by wsidicomizer (`dicomizer_source.py:254-273`, runs after pre-processor/merge so only the post-processor can change it).
3. With (b) pinned via `metadata_post_processor` (set `ContributionDateTime`) and (a) pinned by monkeypatching `wsidicom.file.io.wsidicom_writer.datetime` to a frozen `now()`: **byte-identical outputs across runs**. No other nondeterminism found. (Monkeypatch is a hack; alternatives [U]: rewrite the 2 fixed-width DA/TM values in place post-write, or normalise at ingestion.)
4. Explicit UIDs on `WsiDicomizerMetadata` (Study/Series/Slide sample/FoR) pass through unchanged; SOP UID stays random unless `uid_generator` also given.

## Interaction with repo UID pseudonymization + ingestion dedup
- `helpers/dicom_uid.py`: `hash_uid(uid, salt)` = `"2.25." + decimal(SHA256(uid+salt))`, truncated to 64 chars; salt is per-Research-Project, never rotated [V]. Pure function of (source UID, project salt) -> stable source UIDs give stable pseudonyms. Generated UIDs `2.25.<128-bit decimal>` are <=44 chars, valid [V].
- `pipeline._ingest_file`: pseudonymizes Study/Series/SOP UIDs; **dedup key = `DicomFile.sop_instance_uid == pseudonymized SOP`**, queried **without a project filter** (safe in practice since salt differs per project) [V] (`pipeline.py:239-257`, `records.py` matches Study/Series by pseudonymized UID).
- On a match, `_handle_duplicate` compares SHA-256 of bytes: equal -> `skipped_duplicate`; differing -> `duplicate_conflict` (replaced in place only if project `dicom_duplicate_handling == "update"` or override) [V] (`pipeline.py:302-335`).
- Consequences:
  - Random UIDs (today): each re-conversion = new Study/Series/SOP -> duplicate studies/series, no dedup. [V by reading code + default `CallableUidGenerator`]
  - Deterministic UIDs but timestamps unpinned: re-ingest -> `duplicate_conflict` every time (a no-op write or an in-place update depending on setting). Pin timestamps (exp. 3) to get `skipped_duplicate`.
  - Study UID granularity is a design choice: hash(NDPI) per file = one Study per slide; to group several slides of one patient/case into one Study, derive `study_uid` from a (patient, study identifier) pair, and `series_uid`/FoR/SOP from the NDPI hash. Study/Series fields are fill-blank-only on later matches, so first-ingest values stick [V from `records.py` docstring].
  - Changing converter version/options (levels, tile size, encoding) with the same SOP key but different pixels => same UID, different bytes => conflict. Include a converter/options version in the SOP key if that should be a new instance [U design advice].
  - Ingestion requires non-empty PatientID (`participant.match_or_create_participant` raises ValueError otherwise), so PatientID **must** be injected for converted files to ingest [V].
  - `concatenation_*`/split modes: `sop_uid` is called before concatenation attrs are set, so parts of one level share identical key inputs except `NumberOfFrames`; the key would collide unless it adds a counter. Default (`concatenation=None`, `instance_split=NONE`) not affected. [V from code order; collision U, not run]

## Open / unverified
- Not run: full-level conversion, `InstanceSplit`/`ConcatenationBy*`, non-NDPI sources. [U]
- Not run: actual ingestion of converted output (Django DB not exercised); dedup behaviour inferred from code. [U]
- Behaviour on wsidicomizer/wsidicom versions other than 0.30.0/0.35.0 (the `UidGenerator` ABC looks new; `>=0.30.0` is the only pin). [U]
- Whether a cleaner upstream hook for InstanceCreationDate/Time exists or could be requested. [U]

## Sources (local, primary)
- `.venv/lib/python3.14/site-packages/wsidicomizer/{wsidicomizer.py,dicomizer_source.py,uid_resolver.py,metadata.py,sources/opentile/opentile_metadata.py}`
- `.venv/lib/python3.14/site-packages/wsidicom/{metadata/uid_generator.py,metadata/{patient,study,series,slide,pyramid,sample}.py,metadata/schema/dicom/slide.py,file/file_writer.py,file/io/wsidicom_writer.py,file/io/wsidicom_io.py}`
- `MiqaResearch/tasks/dicom_handling/{ndpi_conversion.py,pipeline.py,records.py,participant.py}`, `helpers/dicom_uid.py`
