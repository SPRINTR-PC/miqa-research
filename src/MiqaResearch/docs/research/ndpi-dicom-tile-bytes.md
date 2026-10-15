# Research: NDPI -> DICOM tile bytes (wsidicomizer / opentile / wsidicom)

Resolves #298 (parent map #296). Findings only; no spec decisions locked.

Versions (repo venv): opentile 0.25.0, wsidicomizer 0.30.0, wsidicom 0.35.0.
Legend: **[S]** = read in installed source. **[E]** = measured: CMU-1.ndpi converted with `WsiDicomizer.convert(src, output_path=...)` (defaults, as in `convert_ndpi_to_dicom`), 2.7 s.
Source paths are under `.venv/lib/python3.14/site-packages/`.

## Short answer

1. **Yes, JPEG bytes are passed through, not re-encoded** (baseline 8-bit JPEG, no transcoding) [S][E]. But DICOM frames are **not the NDPI stripes**: opentile builds each tile by concatenating stripes (restart markers) and lossless-cropping with libjpeg-turbo. The bytes wsidicomizer writes are exactly `opentile get_tile()` output.
2. **Raw byte compare works** between opentile tiles (same `tile_size`) and DICOM frames, with one normalisation: DICOM encapsulation pads odd-length frames with a trailing `0x00`. [E] CMU-1: 4 levels, 8,014 tiles, 0 mismatches; 3,978 (~50%) differ only by that pad byte.
3. It is **not independent** of the crop logic: both sides come from the same opentile crop. It proves "writer wrote what opentile produced", not "opentile's re-tiling is pixel-faithful to the original NDPI". Independent proof needs decode-and-compare against a non-opentile read of the NDPI.
4. Label and overview are kept as separate DICOM instances. Label is a lossless **crop** of the macro image [S][E].

## Pass-through vs transcode

- `OpenTileImageData.get_transfer_syntax` passes through only baseline 8-bit JPEG (1.2.840.10008.1.2.4.50) or Part-1 JPEG 2000. Anything else raises `NotImplementedError` and the image is transcoded via the encoder. `needs_transcoding = not supported or force_transcoding` [S: wsidicomizer/sources/opentile/opentile_image_data.py].
- `get_encoded_tile(s)`: if not transcoding returns `self._tiff_image.get_tile(s)` verbatim; else `get_decoded_tile` + `encoder.encode` [S, same file].
- `convert_ndpi_to_dicom` passes no `encoding`/`force_transcoding`, so default = pass-through. [E] all 6 instances: TransferSyntax 1.2.840.10008.1.2.4.50, `LossyImageCompression=01`, method `ISO_10918_1`, photometric `YBR_FULL_422`.
- `OpenTileSource.__init__` docstring says "Pyramid is always re-encoded using the encoder". Stale; code and [E] show otherwise [S].
- NDPI JPEG XR levels are the exception: opentile exposes native JPEG XR tiles, not DICOM-supported, so wsidicomizer transcodes (decode + encode). Byte compare impossible [S: opentile/formats/ndpi/ndpi_tiler.py `_create_level`, `NdpiJpegXrImage`]. Not present in CMU-1.
- Non-8-bit/extended JPEG likewise falls to transcoding [S].

## Why tile geometry differs and how opentile bridges it

[S: opentile/formats/ndpi/ndpi_tiler.py, ndpi_image.py, ndpi_tile.py]
- NDPI levels are JPEG stripes (restart-marker based) or one single frame (small levels).
- `NdpiTiler(file, tile_size)` adjusts requested size to `2^n * smallest stripe width` (`_adjust_tile_size`). wsidicomizer default `tile_size=512` (`config.default_tile_size`). CMU-1 result: 512.
- `NdpiStripedImage`: reads needed stripes, `Jpeg.concatenate_fragments(stripes, header)` (new header, rewritten restart indices), then `crop_multiple` (libjpeg-turbo lossless crop) to tile_size. Needs libjpeg-turbo >= 2.1 or raises `ValueError` ("Failed to crop...").
- `NdpiOneFrameImage` (single-frame level): header patched to whole MCUs, then `crop_multiple` extends/crops to tile multiple. Image size is taken from the JPEG header when it disagrees with tiff tags.
- Consequence: DICOM frame bytes != any stored NDPI byte range. Raw compare against file stripes is impossible; compare against opentile tiles. Edge tiles are padded to full tile size.
- Crop on MCU boundaries should not re-quantise (opentile design claim; not independently verified here).

## How to read tiles per level

opentile (original side):
```python
from opentile import OpenTile
with OpenTile.open(ndpi_path, tile_size) as t:      # tile_size MUST equal DICOM Rows/Columns
    for lv in t.levels:                              # lv.pyramid_index, lv.tiled_size, lv.image_size
        positions = [(x, y) for y in range(lv.tiled_size.height) for x in range(lv.tiled_size.width)]
        for pos, data in zip(positions, lv.get_tiles(positions)):   # bytes; get_decoded_tiles -> np.ndarray
            ...
```
- Take `tile_size` from the DICOM base level (`wsi.levels.base_level.tile_size.width`) so grids match. [E] opentile sizes/tiled_size equal DICOM.
- `OpenTile.open` is the call wsidicomizer makes. `t.levels` is a list; `level.pyramid_index` is the DICOM level number.

wsidicom / DICOM side:
```python
from wsidicom import WsiDicom
from wsidicom.geometry import Point
with WsiDicom.open(output_dir) as wsi:
    level = wsi.levels.get(lv.pyramid_index)          # pyramid_index, not list position
    idata = level.default_instance.image_data
    data = idata.get_encoded_tile(Point(x, y), idata.default_z, idata.default_path)
```
- **Avoid `WsiDicom.read_encoded_tile` / `WsiInstance.get_encoded_tile` with default `crop_to_image_boundary=True`**: for edge tiles it decodes, crops and **re-encodes** [S: wsidicom/instance/instance.py]. Use `crop_to_image_boundary=False` or `image_data.get_encoded_tile`.
- `image_data.get_encoded_tiles` batches. Frames are read via offset table [S: wsidicom/file/io/wsidicom_reader.py `read_frame`]. Missing tiles return `blank_encoded_tile`; instances here are TILED_FULL [E]. Validator should assert frame_count == tiled_w*tiled_h.
- Alternative without wsidicom: pydicom encapsulated-frame iteration on the `.dcm`. Same pad rule.

## Odd-length padding (must normalise)

- Writer: `pydicom.encaps.itemize_frame` pads odd-length frames with one trailing `0x00` (items must be even length) [S: wsidicom/file/io/wsidicom_writer.py `write_tile`; pydicom/encaps.py].
- Reader: wsidicom takes frame length from item/offset table including the pad; rejects odd lengths [S: frame_index/offset_table.py, pixel_data.py]. So DICOM bytes are `tile` or `tile + b"\x00"`.
- [E] label: DICOM 23220 B vs opentile 23219 B (pad); overview 57144 == 57144.
- Rule: `dicom == tile or (len(tile) % 2 == 1 and dicom == tile + b"\x00")`. Prefer this to blanket `rstrip(b"\x00")`.

## Associated images and metadata

[E] CMU-1 output = 6 instances: 4 VOLUME levels, 1 LABEL, 1 OVERVIEW. No THUMBNAIL (`NdpiTiler._create_thumbnail` raises NotImplementedError).
- Levels: NDPI scales 1/4/16/64 -> DICOM pyramid indices 0/2/4/6. No levels 1/3/5 (`add_missing_levels` default False). Level 0 ImageType ORIGINAL; others DERIVED/RESAMPLED (flags). Match levels by `pyramid_index`/size, not list index.
- Overview = whole NDPI "Macro" image, bytes passed through (1191x408) [S][E equal bytes].
- Label = **crop of Macro** at `label_crop_position=0.3` of width, MCU-aligned (`NdpiLabelImage`, lossless `crop_multiple`): 352x408 from 1191x408 [S][E]. Label pixels are a subset of the macro, not an NDPI-native label. Compare to `t.labels[0].get_tile((0,0))`; independent check: decode Macro, slice columns [0:352].
- Non-JPEG (JPEG XR) macro/label are decoded and served uncompressed [S]; byte compare N/A.
- Pixel spacing: **DICOM DS is <=16 chars, so values are rounded**: opentile 0.00045641259698767686 mm vs DICOM 0.00045641259699 [E]. DICOM PixelSpacing order is [row, col] = [y, x]. Compare with ~1e-12 mm tolerance (or round to DS), not exact; the only field where "no tolerance" cannot hold.
- Magnification: opentile `metadata.magnification` 20.0; DICOM `OpticalPathSequence[0].ObjectiveLensPower` 20.0 [E].
- Other [E]: Manufacturer `Hamamatsu`; ImagedVolumeWidth/Height 23.368 x 17.358 mm.
- Dimensions: DICOM TotalPixelMatrixColumns/Rows == opentile `image_size` for all 4 levels [E].
- Several pyramids in a file raise `NotImplementedError` (`OpenTileSource.pyramid_levels`); NDPI is single-pyramid [S].

## When decode-and-compare is needed

1. Any **transcoded** image (JPEG XR NDPI levels, non-baseline JPEG, `force_transcoding`): compare `get_decoded_tile` (opentile) vs `get_decoded_tile` (wsidicom). Pixel-exact only with a lossless encoder; with a lossy one the original cannot match exactly (contradicts "no tolerance"; flag or reject such inputs).
2. **Independent check of opentile's re-tiling** (stripe concat + crop): bytes-equal-to-opentile does not prove it. Compare decoded DICOM tiles against pixels from another reader (openslide / tifffile) for sampled tiles. Full decode is costly (CMU-1 base 51200x38144 ~ 5.9 GB RGB): sample or stream tiles.
3. Edge tiles: padding is not image; when comparing pixels, restrict to in-image region (`image_region.inside_crop`).
4. Byte mismatch beyond the pad byte: decode both to classify cosmetic (header/marker) vs real.

## Open items / not verified

- Only CMU-1.ndpi tested (JPEG only; striped levels + one single-frame level). JPEG XR NDPI and multi-focal-plane not exercised.
- libjpeg-turbo crop losslessness not checked against an independent decoder.
- Compare cost not benchmarked formally; CMU-1 full byte compare ran well under a minute single-threaded.

## Sources

- opentile 0.25.0: `opentile/formats/ndpi/{ndpi_tiler,ndpi_image,ndpi_tile}.py`, `opentile/jpeg/jpeg.py`, `opentile/tiff_image.py`, `opentile/opentile.py`.
- wsidicomizer 0.30.0: `wsidicomizer/wsidicomizer.py`, `wsidicomizer/sources/opentile/{opentile_source,opentile_image_data}.py`, `wsidicomizer/config.py`.
- wsidicom 0.35.0: `wsidicom/wsidicom.py`, `instance/instance.py`, `instance/wsidicom_image_data.py`, `file/io/{wsidicom_writer,wsidicom_reader}.py`, `file/io/frame_index/*.py`.
- pydicom `encaps.py` (`itemize_frame`). Repo: `MiqaResearch/tasks/dicom_handling/ndpi_conversion.py`.
- Experiment scripts were throwaway (convert + per-tile compare over CMU-1), not committed.
