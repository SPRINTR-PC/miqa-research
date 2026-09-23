"""The ETL Datatype registry (#159): code-registered kinds of incoming data.

Datatypes are never user-defined -- a Data Manager only ever picks one, by name, from this
registry. `@register_datatype` binds a name to an output schema (what a Script's JSONL rows must
match) and a loader (how validated rows get persisted); registering the same name twice is a hard
error, since it would silently shadow whichever Datatype registered first.
"""
from collections.abc import Callable
from dataclasses import dataclass

from ninja import Schema

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
    schema: type[Schema]
    loader: LoaderFunc


_REGISTRY: dict[str, DatatypeRegistration] = {}


def register_datatype(name: str, schema: type[Schema]) -> Callable[[LoaderFunc], LoaderFunc]:
    def decorator(loader: LoaderFunc) -> LoaderFunc:
        if name in _REGISTRY:
            raise DatatypeAlreadyRegistered(f"A Datatype named {name!r} is already registered.")
        _REGISTRY[name] = DatatypeRegistration(name=name, schema=schema, loader=loader)
        return loader
    return decorator


def get_datatype(name: str) -> DatatypeRegistration:
    try:
        return _REGISTRY[name]
    except KeyError:
        raise DatatypeNotRegistered(f"No Datatype is registered under {name!r}.") from None


def registered_datatype_names() -> list[str]:
    return sorted(_REGISTRY)
