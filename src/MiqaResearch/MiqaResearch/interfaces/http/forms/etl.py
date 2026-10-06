"""Validation-only forms for the ETL Pipelines tab's manage actions (#158). These never call
`.save()` -- a view calls `is_valid()`, then hands `cleaned_data` to an Action in
`MiqaResearch.actions.etl` to actually persist anything. Script-version choices, and the project's
max script source size, are passed in pre-computed rather than resolved lazily by the form, since
either would run a synchronous DB query inside an async view.
"""
import json

from django import forms
from django.conf import settings
from django.forms.fields import InvalidJSONInput
from django.utils.translation import gettext_lazy as _

from contract.constants.etl import (
    PIPELINE_BINDING_GROUPING_CHOICES,
    PIPELINE_BINDING_GROUPING_FILE,
    PIPELINE_BINDING_RAW_RETENTION_CHOICES,
    PIPELINE_BINDING_RAW_RETENTION_DELETE,
    PIPELINE_BINDING_RAW_RETENTION_MOVE,
)
from MiqaResearch.etl_config_schema import ConfigSchema, ConfigSchemaInvalid, parse_config_schema


class _ScriptVersionUploadMixin:
    """Shared checks for the two forms that upload an EtlScriptVersion: the `source` file's size,
    and that its extension names a language a sandbox image runs (#166); and the optional config
    schema (#238), which must be a valid JSON Schema object."""

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

    def clean_config_schema(self):
        upload = self.cleaned_data["config_schema"]
        if not upload:
            return None
        try:
            return parse_config_schema(upload.read())
        except ConfigSchemaInvalid as error:
            raise forms.ValidationError(str(error))


def _config_schema_field():
    return forms.FileField(
        label=_("Config schema (optional JSON Schema)"), required=False,
        help_text=_("Bindings' config must satisfy it; leave empty to keep config free-form."),
        widget=forms.ClearableFileInput(attrs={"accept": ".json,application/json"}))


def _datatype_choices() -> list[tuple[str, str]]:
    """The registered ETL Datatypes (#223) -- an in-memory registry, so no DB query in an async view."""
    from MiqaResearch.etl_datatypes import registered_datatype_names

    return [(name, name) for name in registered_datatype_names()]


class EtlScriptCreateForm(_ScriptVersionUploadMixin, forms.Form):
    name = forms.CharField(max_length=100)
    description = forms.CharField(required=False, widget=forms.Textarea)
    datatype = forms.ChoiceField(label=_("Datatype"))
    source = forms.FileField()
    config_schema = _config_schema_field()

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


class EtlScriptVersionCreateForm(_ScriptVersionUploadMixin, forms.Form):
    source = forms.FileField(label=_("Source file"))
    config_schema = _config_schema_field()


CONFIG_FIELD_PREFIX = "config__"


_NO_INITIAL = object()
_UNPARSED = object()


class _ConfigJSONField(forms.JSONField):
    """A JSON box for config: blank (not Django's "null") when there's no value, and what was typed
    shown back as typed -- since a generated field's "null" is a real value (#238)."""

    def bound_data(self, data, initial):
        return None if data is None else InvalidJSONInput(data)

    def prepare_value(self, value):
        return "" if value is None else super().prepare_value(value)


def _generated_config_field(key, prop, *, required, initial=_NO_INITIAL) -> tuple[forms.Field, bool]:
    """A form field for one top-level config-schema property (#238), and whether it shows `initial`
    (the Binding's current value): a value the field can't show -- an empty string in a text box,
    a value outside an enum, a wrong type -- is left for the Additional config box instead. Enums
    and booleans post their JSON encoding; anything that isn't a scalar is entered as JSON."""
    kwargs = {"label": prop.get("title") or key, "required": required, "help_text": prop.get("description", "")}
    if "enum" in prop or prop.get("type") == "boolean":
        values = prop["enum"] if "enum" in prop else [True, False]
        labels = [str(value) for value in values] if "enum" in prop else [_("Yes"), _("No")]
        field = forms.TypedChoiceField(
            choices=[("", "---------"), *((json.dumps(value), label) for value, label in zip(values, labels))],
            coerce=json.loads, empty_value=None, **kwargs)
        shown = initial is not _NO_INITIAL and any(initial == value and type(initial) is type(value)
                                                   for value in values)
        if shown:
            field.initial = json.dumps(initial)
        return field, shown

    match prop.get("type"):
        case "string":
            field, can_show = forms.CharField(**kwargs), lambda value: isinstance(value, str) and value != ""
        case "integer":
            field, can_show = forms.IntegerField(**kwargs), lambda value: type(value) is int
        case "number":
            field, can_show = forms.FloatField(**kwargs), lambda value: type(value) in (int, float)
        case _:
            field, can_show = _ConfigJSONField(widget=forms.Textarea(attrs={"rows": 3}), **kwargs), lambda value: True
    shown = initial is not _NO_INITIAL and can_show(initial)
    if shown:
        field.initial = InvalidJSONInput("null") if initial is None else initial
    return field, shown


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
    config = _ConfigJSONField(
        label=_("Script config (JSON object)"), required=False, widget=forms.Textarea,
        help_text=_("Optional; passed to the script as ctx.config."))
    timeout_seconds_override = forms.IntegerField(label=_("Timeout override (seconds)"), required=False, min_value=1)
    memory_mb_override = forms.IntegerField(label=_("Memory override (MB)"), required=False, min_value=1)
    cpu_millicores_override = forms.IntegerField(label=_("CPU override (millicores)"), required=False, min_value=1)

    def __init__(self, *args, location_grants, script_version_choices, can_choose_delete,
                 current_raw_retention=None, config_schemas=None, config_version_id=None, **kwargs):
        self.location_grants = location_grants
        self.can_choose_delete = can_choose_delete
        self.current_raw_retention = current_raw_retention
        super().__init__(*args, **kwargs)
        self.fields["script_version"].choices = script_version_choices
        # #238: the selected Version's config schema, if it has one, replaces the free-form JSON box
        # with one field per top-level property. `config_version_id` overrides the selection: to read
        # a posted form's config fields as rendered, for a Version since swapped out.
        self.config_version_id = config_version_id or self._selected_script_version_id()
        schema = (config_schemas or {}).get(self.config_version_id)
        self.config_schema = ConfigSchema(schema) if schema is not None else None
        self._config_field_names = {}  # config key -> generated field name
        if self.config_schema is not None:
            self._add_generated_config_fields()

    # Rendered together by `_etl_raw_retention_fields.html`, not in the generic field loop.
    RAW_RETENTION_FIELD_NAMES = ("raw_retention", "confirm_delete", "raw_bucket", "raw_prefix")

    def fields_outside_raw_retention(self):
        """The generic field loop: also leaves out the config fields, which `_etl_binding_config_fields.html`
        renders so they can be swapped when another Script Version is chosen."""
        return [field for field in self
                if field.name not in self.RAW_RETENTION_FIELD_NAMES and not self._is_config_field(field.name)]

    def config_fields(self):
        return [field for field in self if self._is_config_field(field.name)]

    def _is_config_field(self, name) -> bool:
        return name == "config" or name in self._config_field_names.values()

    def _selected_script_version_id(self):
        if self.is_bound:
            return self.data.get(self.add_prefix("script_version"))
        choices = self.fields["script_version"].choices
        return self.initial.get("script_version") or (choices[0][0] if choices else None)

    def _add_generated_config_fields(self):
        properties = self.config_schema.properties
        required = self.config_schema.required
        initial_config = self.initial.get("config") or {}
        generated = {}
        unlisted_config = {key: value for key, value in initial_config.items() if key not in properties}
        for key, prop in properties.items():
            name = self._config_field_names[key] = f"{CONFIG_FIELD_PREFIX}{key}"
            generated[name], shown = _generated_config_field(
                key, prop, required=key in required, initial=initial_config.get(key, _NO_INITIAL))
            if key in initial_config and not shown:
                unlisted_config[key] = initial_config[key]

        names = list(self.fields)
        config_index = names.index("config")
        self.fields = {
            name: generated.get(name) or self.fields[name]
            for name in names[:config_index] + list(generated) + names[config_index:]
        }
        # A schema that allows no other keys drops the box -- unless the Binding's config (or the
        # posted form) still has values no field shows: they then show up there (and fail
        # validation, if they don't fit), rather than silently vanishing on a re-pin.
        if not self.config_schema.allows_unlisted_keys and not unlisted_config and not self._posted_config():
            del self.fields["config"]
        elif properties:
            self.fields["config"].label = _("Additional config (JSON object)")
            self.fields["config"].help_text = _(
                "Keys without a field above, and values those fields can't show, e.g. an empty text.")
            self.initial["config"] = unlisted_config

    def entered_config(self) -> dict:
        """The config typed into a bound form's config fields, as far as it parses -- carried into
        the fields of the Version chosen next."""
        def parsed(name):
            if name not in self.fields:
                return None
            try:
                return self.fields[name].clean(self[name].data)
            except forms.ValidationError:
                return _UNPARSED

        return self._assemble_config(parsed)

    def _assemble_config(self, value_of) -> dict:
        """One config from the Additional config box (or free-form box) plus each generated field
        not left blank; `value_of(field name)` gives a field's value, or _UNPARSED to skip it."""
        extra = value_of("config")
        config = dict(extra) if isinstance(extra, dict) else {}
        for key, name in self._config_field_names.items():
            value = value_of(name)
            if not self._left_blank(name) and value is not _UNPARSED:
                config[key] = value
        return config

    def _left_blank(self, name) -> bool:
        """A blank generated field leaves its key out, so the Script's own default applies."""
        return not (self.data.get(self.add_prefix(name)) or "").strip()

    def _posted_config(self) -> str:
        return (self.data.get(self.add_prefix("config")) or "").strip() if self.is_bound else ""

    def _clean_config_against_schema(self, cleaned):
        """Assembles the generated fields (and any additional keys) into one config, then checks it
        against the selected Version's schema -- so a re-pin is rejected until the config fits."""
        # A field that already failed would only be reported again, as a missing key.
        config_field_names = ("config", *self._config_field_names.values())
        if self.config_schema is None or any(name in self.errors for name in config_field_names):
            return
        config = cleaned["config"] = self._assemble_config(cleaned.get)
        for error in self.config_schema.errors(config):
            field = self._config_field_names.get(error.key)
            if field is None:
                field = "config" if "config" in self.fields else None
            self.add_error(field, error.message)

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
        self._clean_config_against_schema(cleaned)
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
