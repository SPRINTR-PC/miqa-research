class EtlDatatypeError(Exception):
    """Base for a failure in the ETL Datatype registry or loader (#159)."""


class DatatypeAlreadyRegistered(EtlDatatypeError):
    """A second Datatype registered under a name that's already taken."""


class DatatypeNotRegistered(EtlDatatypeError):
    """No Datatype is registered under the requested name."""


class EtlJobProjectMismatch(EtlDatatypeError):
    """The given EtlJob's Binding belongs to a different project than the one passed to load it into."""


class EtlRowError(EtlDatatypeError):
    """A single row failed validation or resolution; the caller rolls back the whole batch."""


class AmbiguousParticipantReference(EtlRowError):
    """A row's Participant Reference matched more than one Study Participant in the project."""


class UnresolvableParticipantReference(EtlRowError):
    """A row's Participant Reference matched no Study Participant in the project."""
