"""Validation-only forms for the ETL Pipelines tab's manage actions (#158). These never call
`.save()` -- a view calls `is_valid()`, then hands `cleaned_data` to an Action in
`MiqaResearch.actions.etl` to actually persist anything. Script-version choices, and the project's
max script source size, are passed in pre-computed rather than resolved lazily by the form, since
either would run a synchronous DB query inside an async view.
"""
from django import forms
from django.conf import settings
from django.utils.translation import gettext_lazy as _


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


class EtlScriptCreateForm(_ScriptSourceSizeMixin, forms.Form):
    name = forms.CharField(max_length=100)
    description = forms.CharField(required=False, widget=forms.Textarea)
    source = forms.FileField()


class EtlScriptEditForm(forms.Form):
    name = forms.CharField(max_length=100)
    description = forms.CharField(required=False, widget=forms.Textarea)


class EtlScriptVersionCreateForm(_ScriptSourceSizeMixin, forms.Form):
    source = forms.FileField()


class EtlBindingCreateForm(forms.Form):
    source_bucket = forms.CharField(max_length=200)
    source_prefix = forms.CharField(max_length=500, required=False)
    script_version = forms.ChoiceField()
    raw_bucket = forms.CharField(max_length=200)
    raw_prefix = forms.CharField(max_length=500, required=False)
    timeout_seconds_override = forms.IntegerField(required=False, min_value=1)
    memory_mb_override = forms.IntegerField(required=False, min_value=1)
    cpu_millicores_override = forms.IntegerField(required=False, min_value=1)

    def __init__(self, *args, location_grants, script_version_choices, **kwargs):
        self.location_grants = location_grants
        super().__init__(*args, **kwargs)
        self.fields["script_version"].choices = script_version_choices

    def clean(self):
        from MiqaResearch.readers.etl_reader import location_grant_allows

        cleaned = super().clean()
        source_bucket = cleaned.get("source_bucket")
        if source_bucket and not location_grant_allows(
                self.location_grants, source_bucket, cleaned.get("source_prefix") or ""):
            self.add_error(
                "source_bucket",
                _("This project has not been granted access to that source bucket/prefix."))
        raw_bucket = cleaned.get("raw_bucket")
        if raw_bucket and not location_grant_allows(
                self.location_grants, raw_bucket, cleaned.get("raw_prefix") or ""):
            self.add_error(
                "raw_bucket",
                _("This project has not been granted access to that raw bucket/prefix."))
        return cleaned


class EtlProjectSettingsForm(forms.Form):
    log_retention_days = forms.IntegerField(required=False, min_value=1)
    max_script_source_bytes = forms.IntegerField(required=False, min_value=1)
