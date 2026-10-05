"""A Script Version's optional config schema (#238): a JSON Schema (Draft 2020-12) its Bindings'
config must satisfy. A Version without one keeps config free-form.
"""
import json

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError


class ConfigSchemaInvalid(ValueError):
    """An uploaded config schema isn't a usable JSON Schema object."""


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


def config_errors(schema: dict | None, config: dict) -> list[tuple[str | None, str]]:
    """Every way `config` fails `schema`, as (offending top-level key or None, message naming the
    key path); none without a schema."""
    if schema is None:
        return []
    errors = sorted(Draft202012Validator(schema).iter_errors(config), key=lambda e: [str(p) for p in e.absolute_path])
    return [(_top_key(error.absolute_path), f"{_path(error.absolute_path)}{error.message}") for error in errors]


def _top_key(path) -> str | None:
    return str(path[0]) if path else None


def _path(path) -> str:
    return f"{'.'.join(str(part) for part in path)}: " if path else ""
