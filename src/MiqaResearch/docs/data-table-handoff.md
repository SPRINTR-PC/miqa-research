# Data Table server-driven pagination, sort & filter — handoff spec

Destination of the wayfinder map "Data Table: server-driven pagination, sort & filter — design spec". Every decision below is settled; an implementing session should not need to reopen any of them. Domain terms (**Data Table**, **Data Table Definition**, **Data Table Pagination**) are defined in `GLOSSARY.md`. Supporting research: branch `research/ninja-async-pagination`, `docs/research/ninja-async-pagination.md` (django-ninja 1.6.3, pinned in `uv.lock`).

Scope: a generic, reusable server-driven Data Table. The consent statistics table is the first consumer and the acceptance case. Other tables adopt the class later (out of scope). Chart endpoints and their casing behaviour are untouched.

## 1. Architecture

```
<data-table dataUrl=…>                       (Lit component, core-wc/data-table)
   │  GET ?page&page_size&sort&<filters>&include_columns
   ▼
view (ninja router)  ──builds──▶  DataTableDefinition   (per request: project, user, options)
   │  returns DataTableSource(queryset, definition)
   ▼
@paginate(DataTablePagination)   ── one unit: validate → filter → sort → slice → count
   │  returns {columns?, rows, pagination}
   ▼
component: snakeToCamelDeep(envelope only) → render
```

- **Paging, sorting and filtering are one unit**, implemented in one `AsyncPaginationBase` subclass, `DataTablePagination`.
- The **Data Table Definition** is the single source for (a) the `columns` metadata sent to the client, (b) the allowlist of sortable/filterable columns and their lookups, (c) the `values()` field list. Anything not declared is rejected.
- Page-number pagination.

## 2. Wire contract

### 2.1 Request (all snake_case, flat query string)

| Param | Meaning |
|---|---|
| `page` | 1-based page number. `>= 1`, declared on `Input` (422 if invalid). |
| `page_size` | Rows per page. Server default per endpoint, hard server maximum. Declared on `Input`. The component's `pageSize` property is the initial value it sends. |
| `sort` | `-col1,col2` — comma-separated accessors, `-` prefix = descending. Max **6** columns (Definition-level constant); more → 400. |
| `include_columns` | `true` on first load (and whenever the component has no columns); pages 2+ omit it. Declared on `Input`. |
| `<col>__icontains`, `<col>`, `<col>__gte`, `<col>__lte`, `<col>__in` | Filters. See §3. `__in` is comma-separated. |

Endpoint-specific params (e.g. `include_pid`) are declared on the view, not on `Input`; they arrive in `**params` of `apaginate_queryset` if needed, and the view uses them to build the Definition.

The component changes from sending `pageSize` to sending `page_size`.

### 2.2 Response

Wire format is snake_case JSON like every other endpoint (ADR 0020 amendment).

```jsonc
{
  "columns": [ /* only when include_columns=true, else null */
    { "accessor": "clinic__clinic_name", "label": "Clinic Name", "data_type": "string",
      "sortable": true, "filter": { "kind": "text" },
      "default_sort": "asc", "default_sort_order": 1 }
  ],
  "rows": [ { "clinic__clinic_name": "…", "consent_signed_date": "2026-03-01T10:15:00+00:00" } ],
  "pagination": { "page": 1, "page_size": 25, "total_pages": 4, "total_items": 92,
                  "has_next": true, "has_previous": false }
}
```

- Column schema aligns to the TS `ColumnDefinition` (`accessor`, `label`, `data_type`, `sortable`, `filter`, `width`, `default_sort`, `default_sort_order`, `html_label`, `hsl_color`). It replaces the Python `DataTableColumnSchema(id, title, dataType)`.
- `data_type` literals are exactly the TS `ColumnDataType`: `string`, `number`, `date`, `datetime`, `boolean`, `mini-barchart` (replaces Python `"str"`/`"datetime"`).
- Dates serialize `YYYY-MM-DD`; datetimes ISO 8601 with UTC offset. The component formats in the browser locale. `mini-barchart` cells carry `list[number]`.
- `pagination`: TS `PaginationMeta.count` is **renamed `totalItems`**; `hasNext`/`hasPrevious` come from the server (not re-derived in the component).

### 2.3 Casing

Mimic the charts: the API stays snake_case and the client converts once per response with `snakeToCamelDeep`, **but on the envelope only (`columns`, `pagination`)**. **Row keys are never converted**: a row key is a column accessor that is also sent back for sort/filter, and consent rows use Django paths like `clinic__clinic_name`, which the converter would mangle. Note `columns[].accessor` values are values, not keys, so they are unaffected.

Move `snake-to-camel.ts` from `src/charts/` to a shared location (e.g. `src/core-wc/` or a `src/shared/` module) and re-export it from the charts barrel (`mireswc-charts.ts`) so nothing breaks.

## 3. Sort and filter semantics

The lookup is derived from the column's **declared filter kind**; the client can never choose a lookup.

| `FilterKind` | Query params | Server lookup |
|---|---|---|
| `text` | `col__icontains=x` | `icontains` |
| `text-exact` | `col=x` | `exact` (case-sensitive). On an encrypted column the Definition names its companion hash field: the server hashes `x` with the deterministic hash and matches the hash field. |
| `numeric` | `col=5` | `exact` |
| `numeric-range` | `col__gte`, `col__lte` | `gte` / `lte` |
| `date-range` | `col__gte`, `col__lte` | `gte` / `lte` on the date; `lte` inclusive of the whole day |
| `dropdown` | `col=v` | `exact` |
| `multi-select` | `col__in=a,b` | `in` |
| `boolean` | `col=true\|false` | `exact` |

- `dropdown` / `multi-select` options are **static in the Definition** and travel in the `columns` metadata. Computed options are deferred until a table needs them.
- **Unknown or disallowed sort/filter keys → HTTP 400** (`HttpError(400, msg)` → `{"detail": msg}`). Never silently ignored: this is a PII table and ignoring a filter would return more rows than asked for. Ninja itself ignores unknown query keys (research §4), so the class must scan `request.GET` for keys that are not declared `Input` fields, not view params, and not a Definition-allowed filter key.
- Filter values that fail type coercion → 400 (not 500).
- **Ordering**: no `sort` → the Definition's declared default sort (from the per-column `default_sort` / `default_sort_order`; the component seeds `_sortState` from the same fields), else `-pk`. The paginator **always appends `pk`** as a unique tiebreaker so pages are stable (`ParticipantConsent.Meta.ordering = ["-consent_signed_date"]` is not unique).

## 4. Data Table Definition

Built **per request** by a function `(project, user, options) -> DataTableDefinition`, so permission-dependent columns are simply absent from the allowlist (a sort/filter on an absent column is a 400).

A Definition holds, per column: `accessor` (a `values()` key, may contain `__`), `label` (translated), `data_type`, `sortable`, `filter` (kind + static options/min/max where relevant), default sort direction/order. It exposes:

- `columns` → serializable column metadata,
- `values_fields` → the field list for `queryset.values(...)`,
- `lookup_for(param_key)` → the Django lookup / kind for an allowed filter key, or "not allowed",
- `default_ordering`, `max_sort_columns`.

Suggested location: `MiqaResearch/data/serializers/data_table.py` for the schemas (already the home of `PaginationMetaSchema` / `DataTableResponseSchema`), and a new module next to it for the Definition and `DataTableSource`. The implementing session may choose exact module names.

## 5. The pagination class (`DataTablePagination`)

Django-ninja 1.6.3 facts that shape it (from `docs/research/ninja-async-pagination.md`):

- Subclass `AsyncPaginationBase`; implement `async def apaginate_queryset(self, queryset, pagination, request, **params)`. **Also stub the sync `paginate_queryset`** — it is still abstract and decoration fails with `TypeError` otherwise.
- `Input(Schema)`: `page`, `page_size`, `sort`, `include_columns`. `class Output(Schema)`: `columns: list[…] | None`, `rows`, `pagination`. Set `items_attribute = "rows"`.
- If `__init__` is overridden, call `super().__init__(**kwargs)`.
- The paginator instance is **shared across requests** — no per-request state on `self`.
- The `queryset` argument is whatever the view returns; the view returns a **`DataTableSource(queryset, definition)`** (not a bare queryset), so the per-request Definition travels with the data. No decorator kwarg or factory is needed (decorator kwargs reach only `__init__`, once).
- Use only async ORM in the class: `async for` over the sliced queryset, `await queryset.acount()`.
- **Materialise rows** into a list before returning (`[row async for row in qs[offset:offset+size]]`); returning an unevaluated queryset under `rows` raises `SynchronousOnlyOperation`.
- `acount()` on a joined `values()` queryset counts join rows; if any Definition column can multiply rows, decide distinct handling (consent columns are all forward FKs, so no multiplication).

## 6. View binding (consent as first consumer)

```python
@router.get("consent_by_clinic/{project_id}/table",
            response=list[dict[str, Any]],
            url_name="dashboard_consent_statistics_table")
@paginate(DataTablePagination)
async def dashboard_consent_table_data(request, project_id: UUID, include_pid: bool = False):
    ...  # load project + roles, build Definition, return DataTableSource(queryset, definition)
```

- **Row schema**: `response=list[dict[str, Any]]` (ninja requires a collection response and would otherwise raise `ConfigError`). A static item schema would drop undeclared keys and duplicate the Definition; instead the `values()` list built from the Definition is the only gate on row keys. Consequence: OpenAPI shows an open object for rows.
- **Route name mismatch to resolve**: the template `templates/01_dashboard/_panel_consent_statistics_table.html` references `dashboard_consent_statistics_table` while the view function is `dashboard_consent_table_data`; the current `url_name` is `dashboard_consent_statistics_table`. Keep `url_name` and template consistent (and rename the function if desired).
- The template's `<data-table>` attributes are camelCase-in-HTML (`dataUrl`, `noDataMessage`, …); keep. Add `page-size` only if a non-default is wanted.

## 7. PID authorization

- PID columns (`study_participant__person_source_value`, `study_participant__name`) are visible to every role that may view the table: Admin, PI, Participant Recruiter, and superusers. Recruiters remain clinic-scoped by the existing row filter. (Domain rule confirmed with the user; narrow to Admin/PI if it changes.)
- PID columns are encrypted with a random IV, so the database can neither sort them nor match a substring. They are **not sortable** (400) and are filterable only by **exact match** (`text-exact` through the hash field): `col=x`, never `col__icontains`.
- `include_pid` stays a **default-`false` opt-in** among eligible users. An ineligible user sending `include_pid=true` gets **403**, not silently omitted columns. The Definition builder / reader is the one place that knows roles.
- **Test required**: PID keys never appear in `rows` (nor in `columns`) for an ineligible user, and sorting/filtering on PID columns as such a user is refused. There is no static row schema acting as a second safety net, so this test is the guard.

## 8. Error handling

Reader and view raise `HttpError` with the real status (403 for role failures, 400 for bad sort/filter, 404 for missing project) — never `{"error": …}` with HTTP 200, which would fail the paginated `Output` schema. The component already treats `!response.success` as its error state, so it needs no special handling beyond reading the status detail if desired.

## 9. Component changes (`.dev-data/webcomponents/src/core-wc/data-table/`)

1. **Request URL** (`_buildRequestUrl`): send `page`, `page_size`; `sort` unchanged (`-col,col`); filter params unchanged; add `include_columns=true` when `_columns` is undefined.
2. **Response handling** (`_loadData`): apply the shared `snakeToCamelDeep` to `{columns, pagination}` only; leave `rows` as returned. Keep columns from the first load across page/sort/filter requests when later responses have `columns: null` (do not overwrite with `_deriveColumnsFromRows`; keep that method only as a fallback when the server sends no columns at all and none were ever loaded).
3. **Types** (`data-table-interfaces.ts`): `PaginationMeta.count` → `totalItems`; `ColumnDefinition` unchanged in shape (the API aligns to it); `DataTableResponse` documents columns as optional/nullable.
4. **Pager** (line ~637): `pagination.count <= pagination.pageSize` → `totalItems`.
5. **Sort seed**: seed `_sortState` from columns' `defaultSort` / `defaultSortOrder` when `initialSort` is not given (the Definition supplies them).
6. Update `data-table.test.ts` for the renamed fields, the `page_size` param, `include_columns` behaviour, and envelope-only conversion (a row key such as `clinic__clinic_name` must survive untouched).
7. Rebuild `static/js/webcomponents/mireswc.js` per the repo's normal web component build.

## 10. Refactor plan for the committed WIP ("WIP: Add consent table data")

The WIP is provisional. Keep: the idea that the reader returns a queryset plus column metadata. Replace / fix:

- View: delete the hand-rolled `Paginator` block and manual `request.GET` parsing (`per_page`, `columns`); use `@paginate(DataTablePagination)`.
- Reader `get_consent_table_data_for_project`: return a `DataTableSource(queryset, definition)` built from a per-request Definition; raise `HttpError` instead of `ValueError`. Bugs to fix on the way:
  - `for key, val in columns` iterates a dict without `.items()`;
  - `.annotate(consent_label=Case())` is an empty `Case` and must go (or be a real expression);
  - `user.is_superuser()` is called as a method — it is an attribute on Django users;
  - the `columns` dict and `values_list` duplicate each other; both collapse into the Definition.
- `check_user_project_role_by_name` (`research_project_reader.py`): `any(required_role or role["name"] in required_role for role in project_roles)` is truthy for any non-empty `required_role`, so any user with any role passes any role check. Fix to `any(role["name"] in required_role for role in project_roles)`. This gates PII, so fix it before shipping the table.
- Serializers: replace `DataTableColumnSchema` and `PaginationMetaSchema` with the aligned versions in §2.2; drop or repurpose `DataTableResponseSchema` (now the class's `Output`).

## 11. Testing strategy

- **Pagination class (unit, async)**: page/page_size bounds and 422s; default and max `page_size`; stable ordering with tiebreaker across pages; multi-column sort and the 6-column cap (400); `-pk` fallback; each filter kind → lookup (§3), including date-range inclusive end-of-day and `__in` splitting; unknown key → 400; disallowed key (e.g. PID column for an ineligible user) → 400; bad value types → 400; `has_next`/`has_previous`/`total_pages` at the boundaries and for an empty result; `columns` present only with `include_columns=true`; rows materialised (no `SynchronousOnlyOperation`).
- **View (integration, real `HttpRequest` via the Django test client)**: role matrix (Admin, PI, Participant Recruiter with clinic scoping, no role → 403, superuser); `include_pid` matrix per §7; ISO datetime serialization; snake_case envelope; error statuses per §8.
- **Component (vitest)**: see §9.6.

## 12. Open items for the implementing session

- Not verified in research: whether `columns` is omitted or `null` under `exclude_none`; behaviour through a real (non-`Mock`) request (the code path is the same). Cover both in the view integration tests.
- Decide `page_size` default and maximum values (suggested: default 25, max 200) and the Definition-level max sort columns constant (**6**, decided).
- Exact module names for the Definition / `DataTableSource` (§4).
- OpenAPI documentation of dynamic filter keys is a known gap (ninja cannot declare them from the class); document them in the view docstring.
