"""Validation-only forms for the ETL Pipelines tab's manage actions (#158). These never call
`.save()` -- a view calls `is_valid()`, then hands `cleaned_data` to an Action in
`MiqaResearch.actions.etl` to actually persist anything. Script-version choices, and the project's
max script source size, are passed in pre-computed rather than resolved lazily by the form, since
either would run a synchronous DB query inside an async view.
"""
import json

from django import forms
from django.conf import settings
from django.core.files.base import ContentFile
from django.forms.fields import InvalidJSONInput
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _

from contract.constants.etl import (
    PIPELINE_BINDING_GROUPING_CHOICES,
    PIPELINE_BINDING_GROUPING_FILE,
    PIPELINE_BINDING_RAW_RETENTION_CHOICES,
    PIPELINE_BINDING_RAW_RETENTION_DELETE,
    PIPELINE_BINDING_RAW_RETENTION_MOVE,
)
from MiqaResearch.etl_config_schema import ConfigSchema, ConfigSchemaInvalid, parse_config_schema

_LANGUAGE_LABELS = {".py": "Python", ".r": "R"}


def language_choices() -> list[tuple[str, str]]:
    """The languages a sandbox image runs (`MIRES_ETL_SCRIPT_IMAGE_KEYS`), keyed by extension (#393)."""
    return [(extension, _LANGUAGE_LABELS.get(extension, extension.lstrip(".").upper()))
            for extension in sorted(settings.ETL_SCRIPT_IMAGE_KEYS)]


_SCRIPT_TEMPLATES = {
    ".py": '''import csv


def main(ctx):
    # Yield one dict per row, with the datatype's field names as keys.
    # ctx.input_dir: folder with the input files; ctx.datatype: datatype name; ctx.config: Binding config.
    pass
''',
    ".r": '''library(jsonlite)

main <- function(ctx) {
  # Call emit(row) once per row, with a named list holding the datatype's field names.
  # ctx$input_dir: folder with the input files; ctx$datatype: datatype name; ctx$config: Binding config.
}
''',
}


def script_template(extension: str) -> str:
    """The starter code a new Script begins with in the editor, per language (#393); empty for a
    language without one."""
    return _SCRIPT_TEMPLATES.get(extension.lower(), "")


def script_source_filename(script_name: str, extension: str) -> str:
    """The stored filename for editor-entered code (#393): the slugified Script name plus the language's
    extension, so typed, pasted and file-loaded code are stored identically. Falls back to `script`."""
    return f"{slugify(script_name) or 'script'}{extension}"


def _with_help(field, popover_id, help_label):
    """Marks a field as having a help popover (#393): the template then renders its label row with a "?"
    button outside any <label> -- inside one, a click on the field or the label text would be forwarded
    to the button and open the popover."""
    field.help_popover = popover_id
    field.help_label = help_label
    return field


def _code_fields():
    return (
        _with_help(
            forms.CharField(label=_("Script code"), widget=forms.Textarea(
                attrs={"data-etl-code-editor": "", "rows": 16, "spellcheck": "false"})),
            "etl-script-code-help", _("How is a script written?")),
        forms.ChoiceField(label=_("Language"), widget=forms.Select(attrs={"data-etl-language": ""})),
    )


class _ScriptVersionUploadMixin:
    """Shared checks for the two forms that create an EtlScriptVersion from editor code (#393): the
    code's size, and its language (which picks the sandbox image, #166); `cleaned_data["source"]`
    is then the code as a named file, so Actions stay oblivious to how it was entered. Also the
    optional config schema (#238), which must be a valid JSON Schema object."""

    def __init__(self, *args, max_source_bytes, script_name=None, **kwargs):
        self.max_source_bytes = max_source_bytes
        self.script_name = script_name
        super().__init__(*args, **kwargs)
        choices = language_choices()
        self.fields["language"].choices = choices
        # The editor starts from the first language's skeleton and swaps it when the language changes
        # while the code is still untouched (static/js/etl-code-editor.js).
        self.fields["source_code"].initial = script_template(choices[0][0]) if choices else ""
        self.fields["source_code"].widget.attrs["data-etl-templates"] = json.dumps(
            {extension: script_template(extension) for extension, _ in choices})

    def clean(self):
        cleaned = super().clean()
        code, extension = cleaned.get("source_code"), cleaned.get("language")
        if code is None or extension is None:
            return cleaned
        data = code.encode()
        if len(data) > self.max_source_bytes:
            self.add_error("source_code", _("Script source must be at most %(max_bytes)d bytes for this project.")
                           % {"max_bytes": self.max_source_bytes})
            return cleaned
        name = self.script_name if self.script_name is not None else cleaned.get("name", "")
        cleaned["source"] = ContentFile(data, name=script_source_filename(name, extension))
        return cleaned

    def clean_config_schema(self):
        text = self.cleaned_data["config_schema"].strip()
        if not text:
            return None
        try:
            return parse_config_schema(text.encode())
        except ConfigSchemaInvalid as error:
            raise forms.ValidationError(str(error))


def _config_schema_field():
    return _with_help(forms.CharField(
        label=_("Config schema (optional JSON Schema)"), required=False,
        help_text=_("Bindings' config must satisfy it; leave empty to keep config free-form."),
        widget=forms.Textarea(attrs={
            "data-etl-code-editor": "", "data-etl-fixed-language": ".json", "rows": 10, "spellcheck": "false"})),
        "etl-config-schema-help", _("What is a config schema?"))


def _datatype_choices() -> list[tuple[str, str]]:
    """The registered ETL Datatypes (#223) -- an in-memory registry, so no DB query in an async view."""
    from MiqaResearch.etl_datatypes import registered_datatype_names

    return [(name, name) for name in registered_datatype_names()]


class EtlScriptCreateForm(_ScriptVersionUploadMixin, forms.Form):
    name = forms.CharField(max_length=100, widget=forms.TextInput(attrs={"placeholder": _("Enter name...")}))
    description = forms.CharField(
        required=False, widget=forms.Textarea(attrs={"placeholder": _("Enter description...")}))
    datatype = forms.ChoiceField(label=_("Datatype"))
    source_code, language = _code_fields()
    config_schema = _config_schema_field()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["datatype"].choices = _datatype_choices()


class EtlScriptEditForm(_ScriptVersionUploadMixin, forms.Form):
    """The Edit script modal's single form: settings plus the code and config schema. The view adds a new
    Version only when the code, language or config schema differ from the latest Version."""

    name = forms.CharField(max_length=100, widget=forms.TextInput(attrs={"placeholder": _("Enter name...")}))
    description = forms.CharField(
        required=False, widget=forms.Textarea(attrs={"placeholder": _("Enter description...")}))
    datatype = forms.ChoiceField(required=False)
    source_code, language = _code_fields()
    config_schema = _config_schema_field()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["datatype"].choices = [("", ""), *_datatype_choices()]


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
                 current_raw_retention=None, config_schemas=None, config_version_id=None, storage_id=None,
                 raw_retention_defaults=None, **kwargs):
        # Version id -> the Raw Retention its Datatype declares as default; the wizard preselects it (#418).
        self.raw_retention_defaults = raw_retention_defaults or {}
        self.location_grants = location_grants
        self.storage_id = storage_id  # the Binding's Connected Storage (#394); grants count only on it
        self.can_choose_delete = can_choose_delete
        self.current_raw_retention = current_raw_retention
        super().__init__(*args, **kwargs)
        self.fields["script_version"].choices = script_version_choices
        # #238: the selected Version's config schema, if it has one, replaces the free-form JSON box
        # with one field per top-level property. `config_version_id` overrides the selection: to read
        # a posted form's config fields as rendered, for a Version since swapped out.
        self.config_version_id = config_version_id or self._selected_script_version_id()
        if not self.is_bound and "raw_retention" not in self.initial:
            default = self.raw_retention_defaults.get(self.config_version_id)
            # Not preselected when it is Delete and the user cannot choose Delete (non-Admin): the field's own
            # initial applies instead. Deliberate: see test_datatype_delete_default_is_not_preselected.
            if default and not (default == PIPELINE_BINDING_RAW_RETENTION_DELETE and self.delete_locked):
                self.fields["raw_retention"].initial = default
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
                self.location_grants, raw_bucket, cleaned.get("raw_prefix") or "",
                storage_id=self._binding_storage_id(cleaned)):
            self.add_error(
                "raw_bucket",
                _("This project has not been granted access to that raw bucket/prefix."))
        return cleaned


    def _binding_storage_id(self, cleaned):
        return self.storage_id


class EtlBindingCreateForm(EtlBindingEditForm):
    """The wizard picks its source from the project's Source Locations (#268) rather than a typed
    bucket/prefix; `cleaned_data["source_location"]` is the chosen `EtlSourceLocation`."""
    source_location = forms.ChoiceField(label=_("Source location"))

    field_order = ["source_location"]

    def __init__(self, *args, source_locations, **kwargs):
        self.source_locations = {str(location.id): location for location in source_locations}
        super().__init__(*args, **kwargs)
        self.fields["source_location"].choices = [
            (location_id, str(location))
            for location_id, location in self.source_locations.items()
        ]

    def _binding_storage_id(self, cleaned):
        location = cleaned.get("source_location")
        return location.storage_id if location is not None else None

    def clean_source_location(self):
        from MiqaResearch.readers.etl_reader import location_grant_allows

        location = self.source_locations[self.cleaned_data["source_location"]]
        # A location is created inside a grant, but a grant can still be removed in the Django admin.
        if not location_grant_allows(
                self.location_grants, location.bucket, location.prefix, storage_id=location.storage_id):
            raise forms.ValidationError(_("This project has not been granted access to that source bucket/prefix."))
        return location


def source_location_prefix(grant_prefix: str, subpath: str) -> str:
    """The Source Location's prefix: the grant's prefix with the sub-path added after it."""
    if not subpath:
        return grant_prefix
    separator = "/" if grant_prefix and not grant_prefix.endswith("/") else ""
    return f"{grant_prefix}{separator}{subpath}"


class EtlSourceLocationForm(forms.Form):
    """A Source Location is based on one of the project's location grants: the grant fixes the storage,
    bucket and prefix, and the sub-path can only extend that prefix."""
    grant = forms.UUIDField()
    name = forms.CharField(max_length=100, widget=forms.TextInput(attrs={"placeholder": _("Enter name...")}))
    subpath = forms.CharField(
        max_length=500, required=False, label=_("Additional prefix"),
        widget=forms.TextInput(attrs={"placeholder": _("Enter prefix...")}),
        help_text=_("Added after the grant's prefix, e.g. redcap/a/."))

    def __init__(self, *args, locked=False, **kwargs):
        """`locked`: editing a location a Binding reads from, where only the name can change."""
        super().__init__(*args, **kwargs)
        if locked:
            self.fields["grant"].required = False

    def clean_subpath(self):
        subpath = self.cleaned_data["subpath"].strip()
        if subpath.startswith("/") or "\\" in subpath or ".." in subpath.split("/"):
            raise forms.ValidationError(_("Use a relative path without '..'."))
        return subpath


class EtlLocationGrantEditForm(forms.Form):
    name = forms.CharField(
        max_length=100, required=False, help_text=_("Optional label for this grant."),
        widget=forms.TextInput(attrs={"placeholder": _("Enter name...")}))


class EtlLocationGrantForm(forms.Form):
    name = forms.CharField(
        max_length=100, required=False, help_text=_("Optional label for this grant."),
        widget=forms.TextInput(attrs={"placeholder": _("Enter name...")}))
    storage = forms.UUIDField(required=False)  # blank: the Default storage
    bucket = forms.CharField(max_length=200, widget=forms.TextInput(attrs={"placeholder": _("Enter bucket path...")}))
    prefix = forms.CharField(
        max_length=500, required=False, help_text=_("Empty grants access to the whole bucket."),
        widget=forms.TextInput(attrs={"placeholder": _("Enter prefix...")}))


class EtlProjectSettingsForm(forms.Form):
    log_retention_days = forms.IntegerField(required=False, min_value=1)
    max_script_source_bytes = forms.IntegerField(required=False, min_value=1)
