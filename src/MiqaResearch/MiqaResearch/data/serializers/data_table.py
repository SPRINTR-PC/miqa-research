from typing import Any

from ninja import Schema


class PaginationMetaSchema(Schema):
    page: int
    page_size: int
    total_pages: int
    total_items: int


class DataTableColumnSchema(Schema):
    id: str
    title: str
    dataType: str


class DataTableResponseSchema(Schema):
    columns: list[DataTableColumnSchema] | None = None
    rows: list[dict[str, Any]]
    pagination: PaginationMetaSchema
