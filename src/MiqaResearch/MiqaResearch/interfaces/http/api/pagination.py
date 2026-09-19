from math import ceil
from typing import Any

from django.http import HttpRequest
from ninja import Field, Schema
from ninja.pagination import AsyncPaginationBase

from MiqaResearch.data.serializers.data_table import DataTableColumnSchema, PaginationMetaSchema
from MiqaResearch.data.serializers.data_table_definition import DataTableSource

DEFAULT_PAGE_SIZE = 25
MAX_PAGE_SIZE = 200


class DataTablePagination(AsyncPaginationBase):
    """
    Server-driven Data Table Pagination: page-number paging over a `DataTableSource`, returning
    `{columns?, rows, pagination}`. The instance is shared across requests, so it keeps no per-request state.
    """
    items_attribute = "rows"

    class Input(Schema):
        page: int = Field(1, ge=1)
        page_size: int | None = Field(None, ge=1, le=MAX_PAGE_SIZE)
        sort: str | None = None
        include_columns: bool = False

    class Output(Schema):
        columns: list[DataTableColumnSchema] | None = None
        rows: list[dict[str, Any]]
        pagination: PaginationMetaSchema

    def __init__(self, page_size: int = DEFAULT_PAGE_SIZE, **kwargs: Any) -> None:
        self.default_page_size = page_size
        super().__init__(**kwargs)

    def paginate_queryset(self, queryset, pagination, request: HttpRequest, **params: Any) -> Any:
        raise NotImplementedError("DataTablePagination is async only")

    async def apaginate_queryset(
            self, queryset: DataTableSource, pagination: Input, request: HttpRequest, **params: Any) -> Any:
        source = queryset  # ninja passes whatever the view returned, here a DataTableSource
        definition = source.definition
        page_size = pagination.page_size or self.default_page_size
        offset = (pagination.page - 1) * page_size

        ordered = source.queryset.order_by(*definition.ordering_for(pagination.sort))
        total_items = await ordered.acount()
        total_pages = ceil(total_items / page_size)

        return {
            "columns": definition.column_schemas if pagination.include_columns else None,
            "rows": [definition.serialize_row(row) async for row in ordered[offset:offset + page_size]],
            "pagination": PaginationMetaSchema(
                page=pagination.page,
                page_size=page_size,
                total_pages=total_pages,
                total_items=total_items,
                has_next=pagination.page < total_pages,
                has_previous=pagination.page > 1,
            ),
        }
