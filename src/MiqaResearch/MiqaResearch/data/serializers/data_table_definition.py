from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any

from django.db.models import QuerySet

from MiqaResearch.data.serializers.data_table import ColumnDataType, DataTableColumnSchema


@dataclass(frozen=True)
class DataTableColumn:
    accessor: str
    label: str
    data_type: ColumnDataType
    sortable: bool = False


@dataclass(frozen=True)
class DataTableDefinition:
    """
    Single per-request declaration of a Data Table: the column metadata sent to the client and the `values()` field
    list. Anything not declared here is not returned.
    """
    columns: tuple[DataTableColumn, ...]
    default_ordering: tuple[str, ...] = ()

    @property
    def column_schemas(self) -> list[DataTableColumnSchema]:
        return [
            DataTableColumnSchema(
                accessor=column.accessor, label=column.label, data_type=column.data_type, sortable=column.sortable)
            for column in self.columns
        ]

    @property
    def values_fields(self) -> list[str]:
        return [column.accessor for column in self.columns]

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
