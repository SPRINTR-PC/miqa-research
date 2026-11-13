"""Schema registry (#412): Datatype row schemas by name. The loader registry lives in the app
(`MiqaResearch.etl_datatypes`); a test keeps the two name sets equal."""
from collections.abc import Callable

from pydantic import BaseModel


class SchemaNotRegistered(Exception):
    """No Datatype schema is registered under the requested name."""


class SchemaAlreadyRegistered(Exception):
    """A second schema registered under a name that's already taken."""


_SCHEMAS: dict[str, type[BaseModel]] = {}


def register_schema(name: str) -> Callable[[type[BaseModel]], type[BaseModel]]:
    def decorator(schema: type[BaseModel]) -> type[BaseModel]:
        if name in _SCHEMAS:
            raise SchemaAlreadyRegistered(f"A Datatype schema named {name!r} is already registered.")
        _SCHEMAS[name] = schema
        return schema
    return decorator


def get_schema(name: str) -> type[BaseModel]:
    try:
        return _SCHEMAS[name]
    except KeyError:
        raise SchemaNotRegistered(f"No Datatype is registered under {name!r}.") from None


def schema_names() -> list[str]:
    return sorted(_SCHEMAS)
