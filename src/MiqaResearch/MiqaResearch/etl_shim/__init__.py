__all__ = [
    "ResultDocument",
    "ScriptContext",
    "ShimResult",
    "read_result_jsonl",
    "run_sandbox",
    "run_script",
]

_SHIM_ATTRS = {"ResultDocument", "ShimResult", "read_result_jsonl", "run_sandbox", "run_script"}


def __getattr__(name: str):
    # Lazy on purpose (PEP 562): `.shim`'s own import graph needs the Django app registry ready
    # (`etl_datatypes` -> `data.models`), which isn't true yet at the point `python -m
    # MiqaResearch.etl_shim` imports this package -- Python always runs a package's `__init__.py`
    # before its `__main__.py`, so `__main__.py`'s own `django.setup()` call happens too late for
    # an eager import here (#161).
    if name == "ScriptContext":
        from .context import ScriptContext
        return ScriptContext
    if name in _SHIM_ATTRS:
        from . import shim
        return getattr(shim, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
