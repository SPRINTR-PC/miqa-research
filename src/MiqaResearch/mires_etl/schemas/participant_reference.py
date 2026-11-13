"""Row-schema building blocks shared by Datatype schemas (#159, #412). Resolution of a reference to a
Study Participant stays in the app (`MiqaResearch.etl_datatypes.participant_reference`)."""
from dataclasses import dataclass
from typing import Annotated, Self

from pydantic import BaseModel, model_validator


class ParticipantReferenceFields(BaseModel):
    person_source_value: str | None = None
    alias1: str | None = None

    @model_validator(mode="after")
    def _exactly_one_reference_field(self) -> Self:
        if bool(self.person_source_value) == bool(self.alias1):
            raise ValueError("exactly one of person_source_value or alias1 must be set")
        return self


@dataclass(frozen=True)
class UidField:
    """`Annotated` marker: this field holds a raw DICOM UID the loader must pseudonymize."""


DicomUid = Annotated[str, UidField()]
