"""The ETL Datatype registry (#159): code-registered kinds of incoming data.

Datatypes are never user-defined -- a Data Manager only ever picks one, by name, from this
registry. Two registries (#412): schemas (what a Script's JSONL rows must match) register by name in
the Django-free `mires_etl.schemas`; loaders (how validated rows get persisted) register by name here
with `@register_loader`. A test keeps the name sets equal. Registering the same loader name twice is a
hard error, since it would silently shadow whichever registered first.
"""
from collections.abc import Callable
from dataclasses import dataclass

from pydantic import BaseModel

from mires_etl.schemas import SchemaNotRegistered, get_schema

from .exceptions import DatatypeAlreadyRegistered, DatatypeNotRegistered


@dataclass(frozen=True)
class LoadResult:
    created: int
    updated: int

    @property
    def total(self) -> int:
        return self.created + self.updated


LoaderFunc = Callable[..., LoadResult]


@dataclass(frozen=True)
class DatatypeRegistration:
    name: str
    schema: type[BaseModel]
    loader: LoaderFunc


_LOADERS: dict[str, LoaderFunc] = {}


def register_loader(name: str) -> Callable[[LoaderFunc], LoaderFunc]:
    def decorator(loader: LoaderFunc) -> LoaderFunc:
        if name in _LOADERS:
            raise DatatypeAlreadyRegistered(f"A Datatype named {name!r} is already registered.")
        _LOADERS[name] = loader
        return loader
    return decorator


def get_datatype(name: str) -> DatatypeRegistration:
    try:
        schema = get_schema(name)
    except SchemaNotRegistered:
        raise DatatypeNotRegistered(f"No Datatype is registered under {name!r}.") from None
    try:
        loader = _LOADERS[name]
    except KeyError:
        raise DatatypeNotRegistered(f"Datatype {name!r} has a schema but no loader.") from None
    return DatatypeRegistration(name=name, schema=schema, loader=loader)


def registered_datatype_names() -> list[str]:
    return sorted(_LOADERS)


def loader_names() -> set[str]:
    return set(_LOADERS)

