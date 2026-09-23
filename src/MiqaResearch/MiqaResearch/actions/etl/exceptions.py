class EtlActionError(Exception):
    """Base for a business-rule violation raised by an ETL action; a view catches it and surfaces
    the message as a form error rather than a 500."""


class EtlScriptStateError(EtlActionError):
    """The target Script isn't in a state this action can operate on: wrong project, native
    (read-only), or already archived."""


class EtlBindingConflict(EtlActionError):
    """The requested source bucket/prefix is already bound by another PipelineBinding."""


class EtlScriptVersionNotUsable(EtlActionError):
    """The chosen EtlScriptVersion isn't usable for this project: neither native nor owned by it,
    or its Script has since been archived."""
