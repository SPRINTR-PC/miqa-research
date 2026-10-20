(heading-ndpi-conversion)=
# NDPI to DICOM conversion cost

`convert_ndpi_to_dicom` (`MiqaResearch/tasks/dicom_handling/ndpi_conversion.py`) turns a
Hamamatsu `.ndpi` whole-slide image into a VL Whole Slide Microscopy DICOM file set. It is
standalone: ingestion runs never call it. This page gives its compute cost, and the cost of
the round-trip validation planned for it, so you can size the machine that runs it.

(heading-ndpi-conversion-benchmark)=
## Benchmark

One run per row on two CC0 OpenSlide samples (the first is the one the tests use), warm
file cache, local SSD, Apple M5 Max (18 cores, 128 GB). Treat these as an order-of-magnitude
guide: one run each, no formal repetition.

| Step | Slide | Wall time | CPU time | Peak memory | Per GB of NDPI (wall) |
|---|---|---|---|---|---|
| Conversion (`convert_ndpi_to_dicom`) | `CMU-1.ndpi` (198 MB, 4 levels, 8,014 tiles) | 7.7 s | 11.4 s | 570 MB | about 39 s |
| Conversion | `Hamamatsu-1.ndpi` (6.9 GB, level 0 188160 x 101376) | 53.2 s | 169.8 s | 979 MB | about 8 s |
| Validation, byte compare of every tile | `CMU-1.ndpi` | 12.0 s | 11.8 s | 322 MB | about 61 s |
| Validation, full decode of every tile (both sides) | `CMU-1.ndpi` | 25.5 s | 25.2 s | 328 MB | about 129 s |

- Conversion output is about 1-2% larger than the source (CMU-1: 6 DICOM files, 203 MB;
  Hamamatsu-1: 8 files, 6.97 GB), from the DICOM wrapper and the label and overview
  instances. The JPEG tiles are not re-encoded, so the cost is I/O plus lossless re-tiling,
  not image compression.
- Conversion uses several cores on a large slide (Hamamatsu-1: CPU time about 3.2x wall
  time). Validation as benchmarked is single-threaded.
- Memory grows slowly with slide size (570 MB to 979 MB for a file 35x larger): tiles are
  streamed, never a whole level.
- **Per-GB cost is not constant.** CMU-1's high per-GB figure is mostly fixed start-up cost
  (imports and setup), which a small file does not amortise. For large slides expect roughly
  8 s of conversion per GB on this hardware (a 2 GB NDPI: about 20 s), and use the CMU-1
  per-GB figure only as an upper bound for small files. Validation was measured on CMU-1
  only; its cost on large slides is not benchmarked and may also scale better than the
  per-GB figures above. A container with fewer or slower cores, or network storage, will be
  slower; measure on the target before relying on these numbers.

(heading-ndpi-conversion-validation)=
## Validation

The round-trip validation is **planned, not yet implemented** (see the NDPI to DICOM
round-trip validation map). The validation rows above come from a throwaway prototype that
reads every tile from the NDPI (`opentile`) and from the DICOM (`wsidicom`):

- **Byte compare** (default): the compressed bytes of each tile are compared without
  decoding. On CMU-1 it took about 1.5x the conversion time.
- **Sampled independent decode** (default, in addition): a few tiles per level are decoded
  through an independent reader (`tifffile`). A prototype took 0.4 s for 49 tiles on CMU-1.
- **Full decode** (optional): every tile on both sides is decoded and compared. The row above
  decodes both sides with the same codec, so it is a lower bound for a full compare through
  an independent reader, which was not benchmarked.

For a small slide like CMU-1, budget about 1.5x the conversion time on top of it for the
default validation (conversion plus validation is about 2.5x conversion alone), and at least
3x on top for the optional full compare. These ratios come from CMU-1 only; benchmark a large
slide before sizing for one.
