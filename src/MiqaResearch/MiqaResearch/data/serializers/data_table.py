from typing import Literal

from ninja import Schema

ColumnDataType = Literal["string", "number", "date", "datetime", "boolean", "mini-barchart", "button"]
SortDirection = Literal["asc", "desc"]
FilterKind = Literal["text", "text-exact", "numeric", "numeric-range", "dropdown", "multi-select", "date-range", "boolean"]


class PaginationMetaSchema(Schema):
    page: int
    page_size: int
    total_pages: int
    total_items: int
    has_next: bool
    has_previous: bool


class FilterOptionSchema(Schema):
    value: str
    label: str


class DataTableFilterSchema(Schema):
    kind: FilterKind
    options: list[FilterOptionSchema] | None = None


class DataTableColumnSchema(Schema):
    accessor: str
    label: str
    data_type: ColumnDataType
    sortable: bool = False
    default_sort: SortDirection | None = None
    default_sort_order: int | None = None
    filter: DataTableFilterSchema | None = None
    button_label: str | None = None  # data_type "button": the cell shows a button with this text when the value is set

