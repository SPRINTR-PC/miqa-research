(heading-ndpi-conversion)=
# NDPI to DICOM conversion cost

`convert_ndpi_to_dicom` (`MiqaResearch/tasks/dicom_handling/ndpi_conversion.py`) turns a
Hamamatsu `.ndpi` whole-slide image into a VL Whole Slide Microscopy DICOM file set. It is
standalone: ingestion runs never call it. This page gives its compute cost, and the cost of
the round-trip validation planned for it, so you can size the machine that runs it.

(heading-ndpi-conversion-benchmark)=
## Benchmark

One run each on `CMU-1.ndpi` (198 MB, 4 pyramid levels, 8,014 tiles; the CC0 OpenSlide
sample the tests use), warm file cache, local SSD, Apple M5 Max (18 cores, 128 GB). Treat
these as an order-of-magnitude guide: one run, one slide, no formal repetition.

| Step | Wall time | CPU time | Peak memory | Per GB of NDPI (wall) |
|---|---|---|---|---|
| Conversion (`convert_ndpi_to_dicom`) | 7.7 s | 11.4 s | 570 MB | about 39 s |
| Validation, byte compare of every tile | 12.0 s | 11.8 s | 322 MB | about 61 s |
| Validation, full decode of every tile (both sides) | 25.5 s | 25.2 s | 328 MB | about 129 s |

- Conversion output: 6 DICOM files, 203 MB (about 2.4% larger than the source, from the
  DICOM wrapper and the label and overview instances). The JPEG tiles are not re-encoded, so
  the cost is I/O plus lossless re-tiling, not image compression.
- Conversion can use more than one core (CPU time exceeds wall time). Validation as
  benchmarked is single-threaded.
- Memory stays flat with slide size: tiles are streamed, never the whole level.
- Cost scales with tile count, so estimate a slide from its file size using the per-GB
  column. A 2 GB NDPI is roughly 80 s to convert, 2 min for a byte compare and 4–5 min for
  a full decode compare on similar hardware. A container with fewer or slower cores, or
  network storage, will be slower; measure on the target before relying on these numbers.

(heading-ndpi-conversion-validation)=
## Validation

The round-trip validation is **planned, not yet implemented** (see the NDPI to DICOM
round-trip validation map). The validation rows above come from a throwaway prototype that
reads every tile from the NDPI (`opentile`) and from the DICOM (`wsidicom`):

- **Byte compare** (default): the compressed bytes of each tile are compared without
  decoding. It adds roughly 1.5x the conversion time.
- **Sampled independent decode** (default, in addition): a few tiles per level are decoded
  through an independent reader. Its cost is small and was not benchmarked.
- **Full decode** (optional): every tile on both sides is decoded and compared. The row above
  decodes both sides with the same codec, so it is a lower bound for a full compare through
  an independent reader, which was not benchmarked.

Budget about 1.5x the conversion time on top of it for the default validation (conversion plus
validation is about 2.5x conversion alone), and at least 3x on top for the optional full
compare.
