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


class EtlBindingConfigInvalid(EtlActionError):
    """The Binding's config doesn't satisfy its Script Version's config schema (#238)."""


class EtlJobStateError(EtlActionError):
    """The target EtlJob can't be manually retried: it didn't fail, or its Binding already has
    another Job pending or running."""


class EtlSourceLocationNotInProject(EtlActionError):
    """A Binding was asked to read from another project's Source Location (#268)."""


class EtlLocationOutsideGrant(EtlActionError):
    """A Source Location's bucket/prefix isn't inside any of the project's location grants (#268)."""


class EtlLocationConflict(EtlActionError):
    """A Source Location name or bucket/prefix, or a location grant, already exists in the project."""


class EtlLocationInUse(EtlActionError):
    """A Source Location a Binding uses, or a grant a location or Binding depends on, can't be deleted."""
