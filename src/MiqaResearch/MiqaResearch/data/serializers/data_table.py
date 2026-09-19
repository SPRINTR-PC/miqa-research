from typing import Literal

from ninja import Schema

ColumnDataType = Literal["string", "number", "date", "datetime", "boolean", "mini-barchart"]


class PaginationMetaSchema(Schema):
    page: int
    page_size: int
    total_pages: int
    total_items: int
    has_next: bool
    has_previous: bool


class DataTableColumnSchema(Schema):
    accessor: str
    label: str
    data_type: ColumnDataType
    sortable: bool = False

