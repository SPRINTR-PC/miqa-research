"""Generic UID pseudonymization of a Datatype row or payload (#418).

Every field annotated `DicomUid` (directly, optional, or as list items) is hashed per project with
`pseudonymize_uid`; nothing else is touched. A new payload class only has to type its UID fields.
"""
import typing

from pydantic import BaseModel

from helpers.dicom_uid import pseudonymize_uid
from mires_etl.schemas import UidField


def _is_uid_annotation(annotation) -> bool:
    if typing.get_origin(annotation) is typing.Annotated:
        return any(isinstance(meta, UidField) for meta in annotation.__metadata__)
    return any(_is_uid_annotation(arg) for arg in typing.get_args(annotation))


def _field_is_uid(field) -> bool:
    return any(isinstance(meta, UidField) for meta in field.metadata) or _is_uid_annotation(field.annotation)


def pseudonymize_model(model: BaseModel, project) -> dict:
    """`model.model_dump()` with every UID field (and every nested model's) replaced by its pseudonym."""
    dumped = model.model_dump()
    for name, field in type(model).model_fields.items():
        value = getattr(model, name)
        if isinstance(value, BaseModel):
            dumped[name] = pseudonymize_model(value, project)
        elif value is not None and _field_is_uid(field):
            dumped[name] = _pseudonymize_value(value, project)
    return dumped


def _pseudonymize_value(value, project):
    if isinstance(value, list):
        return [pseudonymize_uid(item, project) for item in value if str(item).strip()]
    text = str(value).strip()
    return pseudonymize_uid(text, project) if text else value
