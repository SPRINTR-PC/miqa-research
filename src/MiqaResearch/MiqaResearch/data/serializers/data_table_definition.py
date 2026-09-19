from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any

from django.db.models import QuerySet
from ninja.errors import HttpError

from MiqaResearch.data.serializers.data_table import ColumnDataType, DataTableColumnSchema, SortDirection

MAX_SORT_COLUMNS = 6


@dataclass(frozen=True)
class DataTableColumn:
    accessor: str
    label: str
    data_type: ColumnDataType
    sortable: bool = False
    default_sort: SortDirection | None = None
    default_sort_order: int | None = None


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


def _serialize_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return value
