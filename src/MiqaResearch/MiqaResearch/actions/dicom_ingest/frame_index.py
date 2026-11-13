"""Frame offset index (#274): where each frame's bytes sit in a stored DICOM file.

Built once at ingestion (and by the backfill task) so WADO-RS /frames can
serve a frame with one ranged read instead of downloading the whole object.

The index is a list of ``[offset, length]`` pairs, one per frame, as absolute
byte positions in the stored file:

- **Native** (uncompressed) pixel data: the frame's raw pixel bytes, computed
  from Rows × Columns × SamplesPerPixel × BitsAllocated.
- **Encapsulated** pixel data: the span of the frame's fragment *items*,
  item headers included. A frame may span several fragments; `frame_bytes`
  strips the item headers. Frame boundaries come from the Extended Offset
  Table, else the Basic Offset Table, else one fragment per frame (when the
  counts agree), else codestream start markers (JPEG SOI / JPEG 2000 SOC).

An empty list means "indexed, but no servable frames": no pixel data, a
Deflated dataset (offsets are meaningless there), bit-packed frames that don't
start on a byte boundary, or fragments that can't be assigned to frames.
"""
import struct
from dataclasses import dataclass
from typing import BinaryIO

import pydicom
from pydicom.uid import UID, DeflatedExplicitVRLittleEndian

_PIXEL_DATA_TAG = (0x7FE0, 0x0010)
_ITEM_TAG = (0xFFFE, 0xE000)
_UNDEFINED_LENGTH = 0xFFFFFFFF
# Codestream starts: JPEG/JPEG-LS SOI, JPEG 2000 SOC+SIZ, JP2 signature box.
_FRAME_START_MARKERS = (b"\xff\xd8", b"\xff\x4f\xff\x51", b"\x00\x00\x00\x0cjP")


@dataclass(frozen=True)
class FrameIndex:
    transfer_syntax_uid: str
    frames: list[list[int]]

    @property
    def is_encapsulated(self) -> bool:
        return UID(self.transfer_syntax_uid).is_encapsulated


def build_frame_index(fp: BinaryIO) -> FrameIndex:
    """Index the frames of the DICOM file readable from the seekable `fp`."""
    fp.seek(0)
    ds = pydicom.dcmread(fp, stop_before_pixels=True, force=True)
    transfer_syntax = UID(str(getattr(ds.file_meta, "TransferSyntaxUID", "") or ""))
    if not transfer_syntax or transfer_syntax == DeflatedExplicitVRLittleEndian:
        return FrameIndex(str(transfer_syntax), [])
    implicit, little_endian = ds.original_encoding
    endian = "<" if little_endian else ">"
    header = _read_element_header(fp, implicit, endian)
    if header is None or header[0] != _PIXEL_DATA_TAG:
        return FrameIndex(str(transfer_syntax), [])
    _, length, value_start = header
    number_of_frames = int(ds.get("NumberOfFrames") or 1)
    if transfer_syntax.is_encapsulated:
        frames = _encapsulated_frames(fp, ds, value_start, number_of_frames)
    else:
        frames = _native_frames(ds, value_start, length, number_of_frames)
    return FrameIndex(str(transfer_syntax), frames)


def frame_bytes(span: bytes, encapsulated: bool) -> bytes:
    """The frame's data from its indexed span (fragment item headers stripped)."""
    if not encapsulated:
        return span
    data, position = [], 0
    while position + 8 <= len(span):
        (length,) = struct.unpack_from("<I", span, position + 4)
        data.append(span[position + 8 : position + 8 + length])
        position += 8 + length
    return b"".join(data)


def _read_element_header(fp: BinaryIO, implicit: bool, endian: str):
    """(tag, value length, value start) of the data element at fp's position."""
    raw = fp.read(8)
    if len(raw) < 8:
        return None
    group, element = struct.unpack(f"{endian}HH", raw[:4])
    if implicit:
        (length,) = struct.unpack(f"{endian}I", raw[4:])
    elif raw[4:6] in (b"OB", b"OW", b"OF", b"OD", b"OL", b"OV", b"UN", b"SQ", b"UT", b"UC", b"UR"):
        extra = fp.read(4)
        (length,) = struct.unpack(f"{endian}I", extra)
    else:
        (length,) = struct.unpack(f"{endian}H", raw[6:])
    return (group, element), length, fp.tell()


def _native_frames(ds, value_start: int, length: int, number_of_frames: int) -> list[list[int]]:
    try:
        frame_bits = int(ds.Rows) * int(ds.Columns) * int(ds.get("SamplesPerPixel") or 1) * int(ds.BitsAllocated)
    except (AttributeError, TypeError, ValueError):
        return []
    if frame_bits % 8 or length == _UNDEFINED_LENGTH or number_of_frames * frame_bits // 8 > length:
        return []
    frame_size = frame_bits // 8
    return [[value_start + i * frame_size, frame_size] for i in range(number_of_frames)]


def _encapsulated_frames(fp: BinaryIO, ds, value_start: int, number_of_frames: int) -> list[list[int]]:
    fp.seek(value_start)
    bot = _read_item(fp)
    if bot is None:
        return []
    basic_offsets = list(struct.unpack(f"<{bot[1] // 4}I", fp.read(bot[1]))) if bot[1] else []
    first_fragment = fp.tell()
    fragments = []  # (item start, item length incl. header, first bytes of value)
    while (item := _read_item(fp)) is not None:
        start, length = item
        fragments.append((start, 8 + length, fp.read(min(length, 6))))
        fp.seek(start + 8 + length)
    if not fragments:
        return []

    offsets = _extended_offsets(ds) or basic_offsets
    if offsets:
        starts = [first_fragment + offset for offset in offsets]
    elif number_of_frames == 1:
        starts = [fragments[0][0]]
    elif len(fragments) == number_of_frames:
        starts = [fragment[0] for fragment in fragments]
    else:
        starts = [start for start, _, head in fragments if head.startswith(_FRAME_START_MARKERS)]
    if len(starts) != number_of_frames:
        return []

    fragment_starts = {fragment[0] for fragment in fragments}
    if any(start not in fragment_starts for start in starts):
        return []
    end = fragments[-1][0] + fragments[-1][1]
    bounds = starts + [end]
    return [[bounds[i], bounds[i + 1] - bounds[i]] for i in range(number_of_frames)]


def _read_item(fp: BinaryIO):
    """(item start, value length) of the next fragment item, or None at the sequence end."""
    start = fp.tell()
    raw = fp.read(8)
    if len(raw) < 8:
        return None
    group, element, length = struct.unpack("<HHI", raw)
    if (group, element) != _ITEM_TAG or length == _UNDEFINED_LENGTH:
        return None
    return start, length


def _extended_offsets(ds) -> list[int]:
    table = ds.get("ExtendedOffsetTable")
    if not table:
        return []
    return list(struct.unpack(f"<{len(table) // 8}Q", table))
