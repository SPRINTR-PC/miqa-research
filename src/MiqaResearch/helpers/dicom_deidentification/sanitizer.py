"""Apply the De-identification Profile to a pydicom Dataset (ADR 0028)."""
import copy
from collections.abc import Callable

from pydicom.dataelem import DataElement, empty_value_for_VR
from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.sequence import Sequence

from helpers.dicom_uid import get_or_create_hashuid_salt_key, hash_uid

from .profile import (
    APPLIED_OPTIONS,
    BASIC_PROFILE_CODE,
    DEIDENTIFICATION_METHOD,
    Action,
    action_for_public_tag,
    safe_private_elements,
)

_DUMMY_TEXT = "ANONYMIZED"
_DUMMY_BY_VR: dict[str, object] = {
    "DA": "19000101",
    "TM": "000000",
    "DT": "19000101000000",
    "AS": "000D",
    "DS": "0",
    "IS": "0",
    **dict.fromkeys(("US", "SS", "UL", "SL", "UV", "SV", "AT"), 0),
    **dict.fromkeys(("FL", "FD"), 0.0),
    **dict.fromkeys(("OB", "OW", "OD", "OF", "OL", "OV", "UN"), b"\x00\x00"),
}

# Bound on sequence nesting followed; deeper structure is dropped, never kept unsanitized
_MAX_DEPTH = 32

UidMapper = Callable[[str], str]


def deidentify(
    dataset: Dataset,
    *,
    research_project,
    participant_alias: str,
    uids_already_pseudonymized: bool = False,
) -> Dataset:
    """Return a de-identified copy of `dataset` (header and file meta); the input is untouched.

    - `participant_alias`: the Study Participant pseudonym written into
      PatientName and PatientID.
    - `uids_already_pseudonymized`: set for objects whose UIDs are already
      HashUID pseudonyms (viewer-built SR/SEG, #287). The rest of the profile
      still applies, but UIDs are left as they are so references aren't hashed
      twice. De-identifying an already de-identified dataset this way returns
      an equal dataset.

    Pixel Data is carried over by reference, never decoded or copied.
    """
    if uids_already_pseudonymized:
        map_uid: UidMapper = _identity
    else:
        # The key never rotates, so an already-loaded one skips the locking read
        # (WADO series /metadata de-identifies one header per instance).
        salt = research_project.dicom_hashuid_salt_key or get_or_create_hashuid_salt_key(research_project)

        def map_uid(uid: str) -> str:
            return hash_uid(uid, salt)

    walker = _Walker(map_uid, participant_alias)
    result = walker.dataset(dataset, depth=0)
    file_meta = getattr(dataset, "file_meta", None)
    if file_meta is not None:
        result.file_meta = FileMetaDataset(walker.dataset(file_meta, depth=0))
    _mark(result)
    _copy_encoding(dataset, result)
    return result


def _identity(uid: str) -> str:
    return uid


class _Walker:
    def __init__(self, map_uid: UidMapper, participant_alias: str):
        self._map_uid = map_uid
        self._participant_alias = participant_alias
        self._safe_private = safe_private_elements()
        self._safe_creators = {(group, creator) for group, creator, _ in self._safe_private}

    def dataset(self, source: Dataset, depth: int) -> Dataset:
        result = Dataset()
        creators: dict[tuple[int, int], str] = {}
        for element in source:
            if element.tag.is_private:
                kept = self._private(element, creators, depth)
            else:
                kept = self._public(element, action_for_public_tag(int(element.tag)), depth)
            if kept is not None:
                result.add(kept)
        return result

    def _private(self, element: DataElement, creators: dict, depth: int) -> DataElement | None:
        tag = element.tag
        if tag.is_private_creator:
            creator = str(element.value or "").strip()
            creators[(tag.group, tag.element)] = creator
            return copy.copy(element) if (tag.group, creator) in self._safe_creators else None
        creator = creators.get((tag.group, tag.element >> 8))
        if creator is None or (tag.group, creator, tag.element & 0xFF) not in self._safe_private:
            return None
        return self._public(element, Action.KEEP, depth)

    def _public(self, element: DataElement, action: Action, depth: int) -> DataElement | None:
        vr = element.VR
        if action is Action.REMOVE:
            return None
        if vr == "SQ":
            if action is Action.EMPTY:
                return DataElement(element.tag, "SQ", Sequence())
            return self._sequence(element, depth)
        if action is Action.KEEP:
            return copy.copy(element)
        if action is Action.EMPTY:
            return DataElement(element.tag, vr, empty_value_for_VR(vr))
        if action is Action.PARTICIPANT_PSEUDONYM:
            return DataElement(element.tag, vr, self._participant_alias)
        if vr == "UI":
            return self._uid(element)
        if action is Action.PSEUDONYMIZE_UID:
            # A non-UID VR on a UID row (private/UN encoding): drop rather than leak
            return None
        return DataElement(element.tag, vr, _DUMMY_BY_VR.get(vr, _DUMMY_TEXT))

    def _sequence(self, element: DataElement, depth: int) -> DataElement | None:
        if depth >= _MAX_DEPTH:
            return None
        items = [self.dataset(item, depth + 1) for item in element.value or ()]
        return DataElement(element.tag, "SQ", Sequence(items))

    def _uid(self, element: DataElement) -> DataElement:
        value = element.value
        if value is None or value == "":
            return copy.copy(element)
        if isinstance(value, str):
            mapped = self._map_one(value)
        else:
            mapped = [self._map_one(str(item)) for item in value]
        return DataElement(element.tag, "UI", mapped)

    def _map_one(self, uid: str) -> str:
        text = uid.strip().rstrip("\x00")
        return self._map_uid(text) if text else uid


def _mark(dataset: Dataset) -> None:
    dataset.PatientIdentityRemoved = "YES"
    dataset.DeidentificationMethod = list(DEIDENTIFICATION_METHOD)
    codes = [BASIC_PROFILE_CODE] + [(code, meaning) for _, code, meaning in APPLIED_OPTIONS]
    dataset.DeidentificationMethodCodeSequence = [_code_item(code, meaning) for code, meaning in codes]


def _code_item(value: str, meaning: str) -> Dataset:
    item = Dataset()
    item.CodeValue = value
    item.CodingSchemeDesignator = "DCM"
    item.CodeMeaning = meaning
    return item


def _copy_encoding(source: Dataset, target: Dataset) -> None:
    implicit_vr, little_endian = source.original_encoding
    if implicit_vr is not None and little_endian is not None:
        target.set_original_encoding(implicit_vr, little_endian, source.original_character_set)
