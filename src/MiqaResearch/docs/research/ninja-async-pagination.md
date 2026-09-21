# Research: django-ninja `AsyncPaginationBase` capabilities

Resolves issue #129 (parent map #128). **Findings only, no design decisions.**

Pinned version: **django-ninja 1.6.3** (`uv.lock`; installed in `src/MiqaResearch/.venv/lib/python3.14/site-packages/ninja/`). Python 3.14.

Sources:
- **[src]**: installed `ninja/pagination.py` (line numbers are for 1.6.3), plus `ninja/operation.py`, `ninja/params/models.py`, `ninja/parser.py`, `ninja/errors.py`, `ninja/utils.py`.
- **[docs]**: https://django-ninja.dev/guides/response/pagination/. The docs page is not versioned and is thinner than the source. Where they differ, the source wins.
- **[exp]**: run against the installed package, using a throwaway script with in-memory SQLite, `ninja.testing.TestAsyncClient` and `User.objects.values("username", "groups__name")` (a join). The script was not committed. Its results are described inline.

## 1. Contract: Input / Output / items_attribute / signature

- `PaginationBase` defines `class Input(Schema)`, `InputSource = Query(...)`, `class Output(Schema)` with `items: List[Any]` and `count: int`, and `items_attribute = "items"` [src pagination.py:39-49].
- `AsyncPaginationBase` adds the abstract method (pagination.py:76-85):
  ```python
  async def apaginate_queryset(self, queryset, pagination, request, **params) -> Any
  ```
  It also adds the helper `_aitems_count`, which calls `await queryset.all().acount()` and falls back to `len()`.
- **`paginate_queryset` (sync) is still abstract on `AsyncPaginationBase`.** A subclass that only implements `apaginate_queryset` fails at decoration time with `TypeError: Can't instantiate abstract class ... without an implementation for abstract method 'paginate_queryset'` [exp]. A stub is required. The stock async classes implement both.
- `request` **is** passed. The wrapper calls `paginator.apaginate_queryset(items, pagination=pagination_params, request=request, **kwargs)` [src `_inject_pagination`, ~line 640]. The docs show the same `request` + `**params` shape [docs]. Confirmed with `request.GET` reachable inside the method [exp]. (`TestAsyncClient` supplies a `Mock` request. The dev/prod request is a real `HttpRequest`.)
- `Input` is delivered as the `pagination` argument, an instance of `paginator.Input` (Pydantic model). It is validated from the query string before the view runs.
- The return value must be a mapping. The wrapper does `result[paginator.items_attribute] = [... async for ... in evaluate(result[items_attribute])]` [src ~lines 655-660]. Every key in the mapping is validated against `Output`.
- Docs list `items_attribute` as the field holding the results, default `'items'` [docs]. Setting `items_attribute = "rows"` works [exp].

### Extra decorator kwargs and view kwargs
- `@paginate(Cls, **paginator_params)` passes `paginator_params` **to `Cls.__init__` only**. They are instantiated once, at decoration time [src `paginate()` ~566-599, `_inject_pagination` `paginator_class(**paginator_params)`]. They are **not** forwarded to `apaginate_queryset`. Verified: `@paginate(P, definition="DEF")` reaches `__init__(definition=...)`, and `**params` is empty of it [exp].
- `PaginationBase.__init__(self, *, pass_parameter=None, **kwargs)` swallows unknown kwargs. A subclass with its own `__init__` must call `super().__init__(**kwargs)` to keep `pass_parameter` working.
- The `**params` of `apaginate_queryset` are the **view's own resolved kwargs** (path/query params declared on the view, minus `ninja_pagination`). Example: a view with `include_pid: bool = False` gives `params == {"include_pid": True}` [exp]. This is the route for per-request endpoint params. Per-endpoint static config (such as a table definition) can only come through `__init__` kwargs, or via the view.
- `pass_parameter="pg"` additionally injects the parsed Input into the view kwargs, and therefore into `**params` as well [src `view_with_pagination`; docs; exp].
- The paginator instance is shared across requests, so per-request state must not be stored on `self`.

## 2. Adding non-item output fields (`columns`, `pagination` meta)

- Subclass-level `class Output(Schema)` replaces the parent's completely. Declare `columns`, `rows` and `pagination` (with nested `Schema` classes for `total_items`, `total_pages`, `has_next`, `has_previous`) [exp; the `CursorPagination.Output` in src:227-230 does the same with `previous`/`next`/`results`].
- `make_response_paginated` builds the final response schema as `type(f"Paged{Item}", (paginator.Output,), {"__annotations__": {items_attribute: List[item_schema]}})` [src ~line 720]. Consequences:
  - The `items_attribute` annotation in `Output` (e.g. `rows: List[Any]`) is **overridden** by `List[<view's response item schema>]`.
  - The view **must declare `response=List[SomeSchema]`**. Otherwise `_find_collection_response` raises `ConfigError` ("has no collection response") [src ~line 754]. Row items are therefore validated and serialized through that item schema. Row dict keys must match the schema's field names, so undeclared keys are dropped [src, by construction]. Keys containing `__` (e.g. `groups__name`) work as field names [exp].
  - OpenAPI shows component `PagedRow` with `columns`, `rows` (`List[Row]`) and `pagination`, and required fields as declared [exp].
- Non-item fields may be `Optional` with `None` (e.g. `columns` only when `include_columns=true`). The response validated and serialized as `"columns": null` [exp]. Whether a key is omitted rather than null depends on the operation's `exclude_none`, which was not tested.

## 3. Async count/slice on a `values()` queryset with joins; sync-in-async pitfalls

- Stock pattern (`PageNumberPagination.apaginate_queryset`, src:175-193): `items = [obj async for obj in queryset[offset:offset+page_size]]`, then `"count": await self._aitems_count(queryset)`. A sliced `values()` queryset over a join (`groups__name`) worked with both, giving 6 join rows for 3 users [exp].
- `acount()` on a join-multiplied `values()` queryset counts **join rows** (no implicit distinct); this is standard Django behaviour and was confirmed by the row count of 6 [exp].
- Pitfall: the wrapper's `evaluate()` is an async generator that does a plain `for result in results` [src ~line 650]. If `apaginate_queryset` returns an **unevaluated QuerySet** under `items_attribute`, this raises `SynchronousOnlyOperation` [exp]. It must return an already-materialised list (async comprehension inside the method).
- The stock async classes branch on `isinstance(queryset, QuerySet)`, so plain lists work too.
- The view's own return value passes through untouched. A `Status` wrapper is unwrapped and re-wrapped with the paged result [src].
- Non-count `PaginationBase._items_count` (sync `.count()`) must not be called from async code; use `_aitems_count`.
- Any other ORM access in the class (`.exists()`, iterating, `len(qs)`) must use the async API (`aexists`, `async for`, `acount`). Django raises `SynchronousOnlyOperation` otherwise.

## 4. Dynamic (undeclared) query keys vs. validation and OpenAPI

- Query params are parsed by `QueryModel.get_request_data` -> `parser.parse_querydict(request.GET, list_fields, request)`. This builds a dict of **all** keys in the query string [src params/models.py:89-93, parser.py:18-27]. `ParamModel` is a plain Pydantic `BaseModel`, so the default `extra="ignore"` applies. **Unknown query keys do not cause 422**; they are silently dropped from the model. Verified: `?foo__icontains=x&unknown=1` returned 200 [exp].
- Unknown keys remain available on `request.GET` inside `apaginate_queryset`. The raw query string is fully readable there [exp].
- Values are validated only for declared fields. `?page=0` -> 422 (`greater_than_equal`), `?page_size=abc` -> 422 (`int_parsing`). The 422 body is `{"detail": [{"type", "loc": ["query", "page"], "msg", ...}]}` [exp; src errors.py:119-122].
- Because undeclared keys never reach validation, "unknown -> 400" has to be implemented in the pagination class (or the view) itself. Ninja does nothing for it.
- OpenAPI only lists declared parameters. For the test endpoint they were `include_pid, page, page_size, sort, include_columns` [exp]. Dynamic filter keys (`col__icontains` etc.) do not appear in the generated schema, and there is no built-in way to declare them from the pagination class. This is a documentation gap only, not a runtime problem.
- `Input` fields sit on the same flat query namespace as the view's own query params, so name clashes between them are not detected here.

## 5. Raising 400 from inside the pagination class

- `raise HttpError(400, "message")` inside `apaginate_queryset` yields `400 {"detail": "message"}` [exp; src errors.py:61-65 and `_default_http_error` :113-116]. `AsyncOperation.run` wraps the view call in `try/except Exception -> api.on_exception` [src operation.py ~495], and the paginated wrapper is the view function.
- Exception handlers are per `NinjaAPI`. A custom handler for `HttpError` or `ninja.errors.ValidationError` could reshape the body; a `ValidationError` handler covers only 422.
- The default `ValidationError` handler produces 422. Raising `ninja.errors.ValidationError(errors)` from the class would also give 422 (not 400) by default [src errors.py:119-122].
- The same holds for `HttpError(403, ...)` and other codes raised in the view or reader, which propagate the same way.

## Summary table

| Question | Answer (1.6.3) |
|---|---|
| `request` passed to `apaginate_queryset`? | Yes, keyword arg |
| Decorator kwargs delivered where? | `Cls.__init__` only (once, at decoration) |
| Per-request extras? | View's own kwargs arrive as `**params`; `pass_parameter` injects Input |
| Sync `paginate_queryset` required? | Yes (still abstract) |
| Custom `Output` with extra fields? | Yes; `items_attribute` field type is overridden by the view's `response=List[Item]` |
| View must declare `response=List[...]`? | Yes, else `ConfigError` |
| Unevaluated QuerySet in rows? | `SynchronousOnlyOperation`; materialise first |
| Unknown query keys | Ignored, no 422; readable via `request.GET`; not in OpenAPI |
| 400 from class | `HttpError(400, msg)` -> `{"detail": msg}` |

## Not verified

- `exclude_none` interplay for omitted vs null `columns`.
- Behaviour under a real (non-`Mock`) request through the Django test client, although the code path is the same.
- Docs for exactly 1.6.3 (the site is unversioned); the source was treated as authoritative.
