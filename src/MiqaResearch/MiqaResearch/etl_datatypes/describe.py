"""Human-readable description of an ETL Datatype's row schema (#393), for the Script editor's
schema preview: one entry per field plus an example JSONL row a Script should emit."""
import json
from dataclasses import dataclass

from .registry import get_datatype

_PLACEHOLDERS = {
    "string": "text", "integer": 1, "number": 1.5, "boolean": True, "date-time": "2024-01-31T00:00:00Z",
    "date": "2024-01-31",
}


@dataclass(frozen=True)
class SchemaField:
    name: str
    type: str
    required: bool
    description: str


@dataclass(frozen=True)
class DatatypeDescription:
    name: str
    fields: list[SchemaField]
    example_row: str


def _type_name(prop: dict) -> str:
    options = prop.get("anyOf") or [prop]
    names = [_one_type(option) for option in options if option.get("type") != "null"]
    return " | ".join(names) or "any"


def _one_type(prop: dict) -> str:
    if prop.get("format") == "date-time":
        return "datetime"
    return prop.get("format") or prop.get("type", "any")


def _example_value(prop: dict, name: str):
    if prop.get("examples"):
        return prop["examples"][0]
    options = [option for option in (prop.get("anyOf") or [prop]) if option.get("type") != "null"]
    option = options[0] if options else {}
    return _PLACEHOLDERS.get(option.get("format")) or _PLACEHOLDERS.get(option.get("type"), name)


def describe_datatype(name: str) -> DatatypeDescription:
    json_schema = get_datatype(name).schema.model_json_schema()
    required = set(json_schema.get("required", []))
    properties = json_schema.get("properties", {})
    fields = [
        SchemaField(name=field, type=_type_name(prop), required=field in required,
                    description=prop.get("description", ""))
        for field, prop in properties.items()
    ]
    example = {field: _example_value(prop, field) for field, prop in properties.items() if field in required}
    example.update({field: _example_value(prop, field) for field, prop in properties.items() if field not in required})
    return DatatypeDescription(name=name, fields=fields, example_row=json.dumps(example, indent=2))
