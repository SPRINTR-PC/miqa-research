import logging
import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from django.conf import settings
from django.db.models import QuerySet
from ninja.errors import HttpError

from helpers.db_fields import get_deterministic_hash
from MiqaResearch.data.serializers.data_table import (
    ColumnDataType,
    DataTableColumnSchema,
    DataTableFilterSchema,
    FilterKind,
    FilterOptionSchema,
    SortDirection,
)

logger = logging.getLogger("mires")

MAX_SORT_COLUMNS = 6


# Per filter kind: the query-string suffix a client sends and the Django lookup it maps to. The client never chooses
# the lookup.
_FILTER_LOOKUPS: dict[FilterKind, tuple[tuple[str, str], ...]] = {
    "text": (("__icontains", "icontains"),),
    "text-exact": (("", "exact"),),
    "numeric": (("", "exact"),),
    "numeric-range": (("__gte", "gte"), ("__lte", "lte")),
    "date-range": (("__gte", "gte"), ("__lte", "lte")),
    "dropdown": (("", "exact"),),
    "multi-select": (("__in", "in"),),
    "boolean": (("", "exact"),),
}


@dataclass(frozen=True)
class DataTableFilter:
    kind: FilterKind
    options: tuple[tuple[str, str], ...] = ()  # (value, label), static; dropdown and multi-select
    # text-exact on an encrypted column: the companion field holding its deterministic hash. The client's value is
    # hashed server-side and matched against it; the hash field is never exposed.
    hash_field: str | None = None


@dataclass(frozen=True)
class DataTableColumn:
    accessor: str
    label: str
    data_type: ColumnDataType
    sortable: bool = False
    default_sort: SortDirection | None = None
    default_sort_order: int | None = None
    filter: DataTableFilter | None = None


@dataclass(frozen=True)
class DataTableDefinition:
    """
    Single per-request declaration of a Data Table: the column metadata sent to the client and the `values()` field
    list. Anything not declared here is not returned.
    """
    columns: tuple[DataTableColumn, ...]
    max_sort_columns: int = MAX_SORT_COLUMNS

    @property
    def column_schemas(self) -> list[DataTableColumnSchema]:
        return [
            DataTableColumnSchema(
                accessor=column.accessor,
                label=column.label,
                data_type=column.data_type,
                sortable=column.sortable,
                default_sort=column.default_sort,
                default_sort_order=column.default_sort_order,
                filter=_filter_schema(column.filter),
            )
            for column in self.columns
        ]

    @property
    def values_fields(self) -> list[str]:
        return [column.accessor for column in self.columns]

    def ordering_for(self, sort: str | None) -> list[str]:
        """
        The `order_by` arguments for a `sort` request (`-col1,col2`), or the declared default sort when none is given,
        else descending primary key. Unknown or non-sortable columns and too many columns are a 400. A unique `pk`
        tiebreaker is always appended so pages are stable.
        """
        requested = [part.strip() for part in sort.split(",")] if sort and sort.strip() else []
        if len(requested) > self.max_sort_columns:
            raise HttpError(400, f"Cannot sort by more than {self.max_sort_columns} columns")

        if requested:
            sortable = {column.accessor for column in self.columns if column.sortable}
            accessors = [part.removeprefix("-") for part in requested]
            for accessor in accessors:
                if accessor not in sortable:
                    raise HttpError(400, f"Cannot sort by '{accessor}'")
            if len(set(accessors)) != len(accessors):
                raise HttpError(400, "Cannot sort by the same column more than once")
            ordering = requested
        else:
            defaults = sorted(
                (column for column in self.columns if column.default_sort),
                key=lambda column: len(self.columns) if column.default_sort_order is None else column.default_sort_order,
            )
            ordering = [("-" if column.default_sort == "desc" else "") + column.accessor for column in defaults]

        if not ordering:
            return ["-pk"]
        if "pk" not in {part.removeprefix("-") for part in ordering}:
            ordering.append("pk")
        return ordering

    def filter_for(self, param_key: str, values: list[str]) -> tuple[str, Any] | None:
        """
        The Django `(filter key, value)` for an allowed filter query parameter, or None when the key is not an allowed
        filter of this Definition. A repeated key or a value that cannot be coerced to the column's type is a 400.
        """
        for column in self.columns:
            if column.filter is None:
                continue
            for suffix, lookup in _FILTER_LOOKUPS[column.filter.kind]:
                if param_key != column.accessor + suffix:
                    continue
                if len(values) != 1:
                    raise HttpError(400, f"Filter '{param_key}' must be given exactly once")
                return self._filter_kwarg(column, column.filter, lookup, param_key, values[0])
        return None

    @staticmethod
    def _filter_kwarg(
            column: DataTableColumn, table_filter: DataTableFilter, lookup: str, param_key: str, raw: str
    ) -> tuple[str, Any]:
        def invalid() -> HttpError:
            return HttpError(400, f"Invalid value for filter '{param_key}'")

        allowed = {value for value, _label in table_filter.options}
        match table_filter.kind:
            case "text":
                return f"{column.accessor}__icontains", raw
            case "text-exact":
                if not raw:
                    raise invalid()
                if not table_filter.hash_field:
                    return column.accessor, raw
                if not settings.SENSITIVE_DATA_HASH_KEY:
                    logger.error("Cannot filter '%s': SENSITIVE_DATA_HASH_KEY is not configured", param_key)
                    raise HttpError(503, "Exact-match filtering on this column is currently unavailable")
                return table_filter.hash_field, get_deterministic_hash(raw)
            case "numeric" | "numeric-range":
                key = column.accessor if lookup == "exact" else f"{column.accessor}__{lookup}"
                number = _parse_number(raw)
                if number is None:
                    raise invalid()
                return key, number
            case "date-range":
                try:
                    if not _ISO_DATE.fullmatch(raw):
                        raise ValueError(raw)
                    day = date.fromisoformat(raw)
                except ValueError:
                    raise invalid() from None
                # A datetime column is compared on its date, so `lte` includes the whole end day.
                path = f"{column.accessor}__date" if column.data_type == "datetime" else column.accessor
                return f"{path}__{lookup}", day
            case "dropdown":
                if allowed and raw not in allowed:
                    raise invalid()
                return column.accessor, raw
            case "multi-select":
                members = raw.split(",")
                if any(not member for member in members) or (allowed and not allowed.issuperset(members)):
                    raise invalid()
                return f"{column.accessor}__in", members
            case "boolean":
                if raw.lower() not in ("true", "false"):
                    raise invalid()
                return column.accessor, raw.lower() == "true"
        raise invalid()  # pragma: no cover

    def serialize_row(self, row: dict[str, Any]) -> dict[str, Any]:
        """
        Dates as YYYY-MM-DD, datetimes as ISO 8601 with a UTC offset.
        """
        return {key: _serialize_value(value) for key, value in row.items()}


@dataclass(frozen=True)
class DataTableSource:
    """
    What a Data Table view returns: the queryset together with the Definition it was built from.
    """
    queryset: QuerySet
    definition: DataTableDefinition


def _filter_schema(table_filter: DataTableFilter | None) -> DataTableFilterSchema | None:
    if table_filter is None:
        return None
    return DataTableFilterSchema(
        kind=table_filter.kind,
        options=[FilterOptionSchema(value=value, label=label) for value, label in table_filter.options] or None,
    )


_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
_MAX_MAGNITUDE_DIGITS = 18  # keeps values within what the database can compare against


def _parse_number(raw: str) -> int | Decimal | None:
    try:
        number: int | Decimal = int(raw)
    except ValueError:
        try:
            number = Decimal(raw)
        except InvalidOperation:
            return None
        if not number.is_finite():
            return None
    magnitude_digits = len(str(abs(number))) if isinstance(number, int) else number.adjusted() + 1
    return number if magnitude_digits <= _MAX_MAGNITUDE_DIGITS else None


def _serialize_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return value
