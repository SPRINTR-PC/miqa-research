"""Validation-only forms for the ETL Pipelines tab's manage actions (#158). These never call
`.save()` -- a view calls `is_valid()`, then hands `cleaned_data` to an Action in
`MiqaResearch.actions.etl` to actually persist anything. Script-version choices, and the project's
max script source size, are passed in pre-computed rather than resolved lazily by the form, since
either would run a synchronous DB query inside an async view.
"""
from django import forms
from django.conf import settings
from django.utils.translation import gettext_lazy as _

from contract.constants.etl import (
    PIPELINE_BINDING_GROUPING_CHOICES,
    PIPELINE_BINDING_GROUPING_FILE,
    PIPELINE_BINDING_RAW_RETENTION_CHOICES,
    PIPELINE_BINDING_RAW_RETENTION_DELETE,
    PIPELINE_BINDING_RAW_RETENTION_MOVE,
)


class _ScriptSourceSizeMixin:
    """Shared `source` checks for the two forms that accept an EtlScriptVersion upload: its size,
    and that its file extension names a language a sandbox image runs (#166)."""

    def __init__(self, *args, max_source_bytes, **kwargs):
        self.max_source_bytes = max_source_bytes
        super().__init__(*args, **kwargs)

    def clean_source(self):
        from MiqaResearch.etl_sandbox.images import image_key_for_script_filename

        source = self.cleaned_data["source"]
        if image_key_for_script_filename(source.name) is None:
            supported = " or ".join(sorted(settings.ETL_SCRIPT_IMAGE_KEYS))
            raise forms.ValidationError(
                _("Script source must be a %(extensions)s file.") % {"extensions": supported})
        if source.size > self.max_source_bytes:
            raise forms.ValidationError(
                _("Script source must be at most %(max_bytes)d bytes for this project.")
                % {"max_bytes": self.max_source_bytes})
        return source


def _datatype_choices() -> list[tuple[str, str]]:
    """The registered ETL Datatypes (#223) -- an in-memory registry, so no DB query in an async view."""
    from MiqaResearch.etl_datatypes import registered_datatype_names

    return [(name, name) for name in registered_datatype_names()]


class EtlScriptCreateForm(_ScriptSourceSizeMixin, forms.Form):
    name = forms.CharField(max_length=100)
    description = forms.CharField(required=False, widget=forms.Textarea)
    datatype = forms.ChoiceField(label=_("Datatype"))
    source = forms.FileField()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["datatype"].choices = _datatype_choices()


class EtlScriptEditForm(forms.Form):
    name = forms.CharField(max_length=100)
    description = forms.CharField(required=False, widget=forms.Textarea)
    datatype = forms.ChoiceField(required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["datatype"].choices = [("", ""), *_datatype_choices()]


class EtlScriptVersionCreateForm(_ScriptSourceSizeMixin, forms.Form):
    source = forms.FileField()


class EtlBindingEditForm(forms.Form):
    """Everything about a Binding but its source bucket/prefix, which is its identity and never
    changes (#224). `EtlBindingCreateForm` adds the source fields on top."""
    script_version = forms.ChoiceField(label=_("Script & version"))
    raw_retention = forms.ChoiceField(
        label=_("After a successful load"), choices=PIPELINE_BINDING_RAW_RETENTION_CHOICES,
        initial=PIPELINE_BINDING_RAW_RETENTION_MOVE, widget=forms.RadioSelect)
    confirm_delete = forms.BooleanField(
        label=_("I understand inputs will not be kept after a successful load."), required=False)
    raw_bucket = forms.CharField(max_length=200, required=False)
    raw_prefix = forms.CharField(max_length=500, required=False)
    grouping_mode = forms.ChoiceField(
        label=_("Grouping"), choices=PIPELINE_BINDING_GROUPING_CHOICES, initial=PIPELINE_BINDING_GROUPING_FILE)
    quiescence_seconds = forms.IntegerField(
        label=_("Quiescence (seconds, folder grouping only)"), required=False, min_value=1)
    config = forms.JSONField(label=_("Script config (JSON object)"), required=False, widget=forms.Textarea)
    timeout_seconds_override = forms.IntegerField(label=_("Timeout override (seconds)"), required=False, min_value=1)
    memory_mb_override = forms.IntegerField(label=_("Memory override (MB)"), required=False, min_value=1)
    cpu_millicores_override = forms.IntegerField(label=_("CPU override (millicores)"), required=False, min_value=1)

    def __init__(self, *args, location_grants, script_version_choices, can_choose_delete,
                 current_raw_retention=None, **kwargs):
        self.location_grants = location_grants
        self.can_choose_delete = can_choose_delete
        self.current_raw_retention = current_raw_retention
        super().__init__(*args, **kwargs)
        self.fields["script_version"].choices = script_version_choices

    @property
    def confirm_delete_required(self) -> bool:
        """Choosing "delete" asks for confirmation only when entering it, not when re-saving a
        Binding that already deletes."""
        return self.current_raw_retention != PIPELINE_BINDING_RAW_RETENTION_DELETE

    @property
    def delete_locked(self) -> bool:
        return self.confirm_delete_required and not self.can_choose_delete

    def clean_config(self):
        config = self.cleaned_data["config"]
        if config is None:
            return {}
        if not isinstance(config, dict):
            raise forms.ValidationError(_("Script config must be a JSON object, e.g. {\"delimiter\": \";\"}."))
        return config

    def clean(self):
        from MiqaResearch.readers.etl_reader import location_grant_allows

        cleaned = super().clean()
        if cleaned.get("raw_retention") == PIPELINE_BINDING_RAW_RETENTION_DELETE:
            if self.delete_locked:
                self.add_error("raw_retention", _("Only a project Admin can choose Delete after load."))
            elif self.confirm_delete_required and not cleaned.get("confirm_delete"):
                self.add_error(
                    "confirm_delete", _("Confirm that inputs will be deleted, not kept, after a successful load."))
            cleaned["raw_bucket"] = cleaned["raw_prefix"] = ""
            return cleaned

        raw_bucket = cleaned.get("raw_bucket")
        if not raw_bucket:
            self.add_error("raw_bucket", _("A raw bucket is required when inputs are moved to a Raw Bucket."))
        elif not location_grant_allows(
                self.location_grants, raw_bucket, cleaned.get("raw_prefix") or ""):
            self.add_error(
                "raw_bucket",
                _("This project has not been granted access to that raw bucket/prefix."))
        return cleaned


class EtlBindingCreateForm(EtlBindingEditForm):
    source_bucket = forms.CharField(max_length=200)
    source_prefix = forms.CharField(max_length=500, required=False)

    field_order = ["source_bucket", "source_prefix"]

    def clean(self):
        from MiqaResearch.readers.etl_reader import location_grant_allows

        cleaned = super().clean()
        source_bucket = cleaned.get("source_bucket")
        if source_bucket and not location_grant_allows(
                self.location_grants, source_bucket, cleaned.get("source_prefix") or ""):
            self.add_error(
                "source_bucket",
                _("This project has not been granted access to that source bucket/prefix."))
        return cleaned


class EtlProjectSettingsForm(forms.Form):
    log_retention_days = forms.IntegerField(required=False, min_value=1)
    max_script_source_bytes = forms.IntegerField(required=False, min_value=1)
