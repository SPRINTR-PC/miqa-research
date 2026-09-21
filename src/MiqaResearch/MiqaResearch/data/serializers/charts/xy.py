from typing import Literal

from ninja import Schema

from MiqaResearch.data.serializers.charts.base import ChartResponseSchema


class XYSeriesSchema(Schema):
    name: str
    x: list[int | float | str]
    y: list[float]
    size: list[float] | None = None  # bubble only — marker size per point
    fill: Literal["none", "tozeroy", "tonexty"] | None = None  # filled area only
    stackgroup: str | None = None  # filled area only — series with the same stackgroup will be stacked
    hovertemplate: str | list[str] | None = None # optional hover template for the series


class XYChartDataSchema(Schema):
    series: list[XYSeriesSchema]


# Four distinct aliases over the same XYChartDataSchema — for symmetry with the
# four distinct Lit elements and routes, not because the underlying shape differs.
LineChartResponseSchema = ChartResponseSchema[XYChartDataSchema]
ScatterChartResponseSchema = ChartResponseSchema[XYChartDataSchema]
BubbleChartResponseSchema = ChartResponseSchema[XYChartDataSchema]
FilledAreaChartResponseSchema = ChartResponseSchema[XYChartDataSchema]
