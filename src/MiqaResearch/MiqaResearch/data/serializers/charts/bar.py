from typing import Literal

from ninja import Schema

from MiqaResearch.data.serializers.charts.base import ChartConfigSchema, ChartResponseSchema


class BarSeriesSchema(Schema):
    name: str
    values: list[float]  # aligned with BarChartDataSchema.categories


class BarChartDataSchema(Schema):
    categories: list[str]
    series: list[BarSeriesSchema]  # length 1 = plain (non-grouped/stacked) bar chart


class BarChartConfigSchema(ChartConfigSchema):
    bar_mode: Literal["group", "stack"] | None = None  # default "group"
    orientation: Literal["v", "h"] | None = None  # default "v"


class BarChartResponseSchema(ChartResponseSchema[BarChartDataSchema]):
    config: BarChartConfigSchema | None = None
