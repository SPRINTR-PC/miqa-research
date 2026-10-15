# Research: DICOM→NDPI writer feasibility

Resolves #297 (parent #296). Findings + recommendation. No spec decisions locked here.

Legend: **[F]** fetched from primary source this session. **[S]** web search only, not fetched. **[M]** maintainer knowledge, unverified. **[X]** fetch failed (403).

## Sources
- OpenSlide Hamamatsu format page: https://openslide.org/formats/hamamatsu/ [F]
- OpenSlide driver source: https://github.com/openslide/openslide/blob/main/src/openslide-vendor-hamamatsu.c [F]
- Bio-Formats NDPI page: https://bio-formats.readthedocs.io/en/stable/formats/hamamatsu-ndpi.html [F]
- NDPITools: https://pperso.ijclab.in2p3.fr/page_perso/Deroulers/software/ndpitools/ [X, 403; only seen via search snippet: NDPI→TIFF direction]
- Hamamatsu NDP.view 2 manual: https://www.hamamatsu.com/content/dam/hamamatsu-photonics/sites/static/sys/en/manual/NDPview2_manual_en.pdf [S: viewer only]
- Hamamatsu SDK (arXiv 2008.06837 describes Java wrappers, SDK under license agreement; read/split only): https://arxiv.org/pdf/2008.06837 [S]

## Does a writer exist?
No public one found.
- Bio-Formats: Export = No; only NDPIReader/NDPISReader [F].
- OpenSlide: read-only [F].
- Hamamatsu: NDP.view 2 is a viewer; SDK is license-gated, described as read/split/extract, no write documented [S].
- NDPITools: NDPI→TIFF (reverse direction) [S/X].
- No DICOM→NDPI tool turned up. Absence of evidence from search; Hamamatsu SDK terms not checked (could contain a writer; ask vendor if it matters).

## Format facts relevant to building one [F, OpenSlide]
- No public spec. All knowledge is reverse-engineered by OpenSlide; many tags "unknown" (65425, 65430, 65433, 65439–65457).
- TIFF hybrid: stock libtiff can't read it (RowsPerStrip = image height overflow; unsorted tags; ASCII always out-of-line).
- 64-bit: high offset bits in a 4-byte-per-entry array after each directory; next-IFD offsets extended to 64 bit; inline values stay inline.
- Each level = exactly one strip holding one JPEG; levels >65535 px per side store width/height as 0 in SOF (invalid for libjpeg).
- Random access via restart markers; offsets in private tags 65426 (low 32) / 65432 (high 32); lower levels may lack restart markers; TIFF vs JPEG dims can disagree.
- Private tags: 65420 format flag (reader rejects file without it), 65421 SourceLens (-1 macro), 65422/65423 offsets, 65424 focal plane, 65427 Reference, 65449 key=value property map, 65459 compression label.
- Reader validation: level widths strictly decreasing; restart interval must divide MCUs/row.

## Feasibility / size
- Writing a file OpenSlide/opentile accept: moderate, est. 1–2 weeks [M]. Needs custom TIFF/BigTIFF-like IFD writer, tags above, single-JPEG-per-level with restart markers and MCU-start tags.
- Hard part: DICOM stores tiled JPEG tiles; NDPI wants one JPEG stream per level (re-wrap tiles into one stream with restart markers needs matching Huffman/quant tables and MCU-aligned tiles; otherwise re-encode, which destroys pixel-exactness). Source NDPI levels >65535 px need the 0-dimension SOF quirk.
- Byte-identical reproduction of the original NDPI is not realistic: scanner-private tags (unknown semantics, Reference/AuthCode), label/macro, unknown tags. Issue #296 already excludes private tags.
- Even if built, a "valid" result only proves our reader-of-record (OpenSlide/opentile) accepts it; it would not prove Hamamatsu software does. Round trip would be self-confirming and share our reverse-engineering assumptions.
- Writer = permanent maintenance liability for a format with no spec, for validation-only value.

## Recommendation
Do not build a DICOM→NDPI writer. Use read-back-and-compare as already leaning in #296: read DICOM with `wsidicom`, original NDPI with `opentile`, compare per-level dims, spacing, magnification, and raw compressed tile bytes where directly comparable (decode otherwise). Revisit only if Hamamatsu confirms an SDK writer (ask vendor) and a real downstream need to emit NDPI appears.
