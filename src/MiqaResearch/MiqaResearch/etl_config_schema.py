"""A Script Version's optional config schema (#238): a JSON Schema (Draft 2020-12) its Bindings'
config must satisfy. A Version without one keeps config free-form.
"""
import json
from typing import NamedTuple

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError


class ConfigSchemaInvalid(ValueError):
    """An uploaded config schema isn't a usable JSON Schema object."""


class ConfigError(NamedTuple):
    key: str | None
    """The offending top-level config key, or None when the error is about the config as a whole."""
    message: str
    """Names the full key path, e.g. "columns.name: 5 is not of type 'string'"."""


def parse_config_schema(raw: bytes) -> dict:
    try:
        schema = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ConfigSchemaInvalid(f"The config schema is not valid JSON: {error}")
    if not isinstance(schema, dict):
        raise ConfigSchemaInvalid("The config schema must be a JSON object.")
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as error:
        raise ConfigSchemaInvalid(f"The config schema is not a valid JSON Schema: {error.message}")
    return schema


class ConfigSchema:
    """The parts of a config schema the Binding forms build on: its top-level properties, which
    of them are required, whether other keys are allowed -- and the check itself."""

    def __init__(self, schema: dict):
        self.schema = schema

    @property
    def properties(self) -> dict[str, dict]:
        return {key: prop for key, prop in (self.schema.get("properties") or {}).items() if isinstance(prop, dict)}

    @property
    def required(self) -> set[str]:
        return set(self.schema.get("required") or [])

    @property
    def allows_unlisted_keys(self) -> bool:
        return self.schema.get("additionalProperties") is not False

    def errors(self, config: dict) -> list[ConfigError]:
        errors = sorted(
            Draft202012Validator(self.schema).iter_errors(config), key=lambda e: [str(p) for p in e.absolute_path])
        return [ConfigError(_top_key(error.absolute_path), f"{_path(error.absolute_path)}{error.message}")
                for error in errors]


def _top_key(path) -> str | None:
    return str(path[0]) if path else None


def _path(path) -> str:
    return f"{'.'.join(str(part) for part in path)}: " if path else ""
