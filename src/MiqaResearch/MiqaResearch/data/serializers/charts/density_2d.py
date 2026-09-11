from typing import Literal

from ninja import Schema

from MiqaResearch.data.serializers.charts.base import ChartConfigSchema, ChartResponseSchema


class Density2DBinsSchema(Schema):
    nbinsx: int | None = None
    nbinsy: int | None = None
    xbins: dict | None = None
    ybins: dict | None = None


class Density2DSeriesSchema(Schema):
    name: str
    x: list[float]  # raw scattered point pairs — no server-side pre-aggregation
    y: list[float]
    bins: Density2DBinsSchema | None = None  # overrides Density2DChartConfigSchema.density_bins


class Density2DChartDataSchema(Schema):
    series: list[Density2DSeriesSchema]  # multi-series overlay in scope, like histogram


class Density2DChartConfigSchema(ChartConfigSchema):
    style: Literal["heatmap", "contour"] | None = None  # default "heatmap"
    density_bins: Density2DBinsSchema | None = None  # chart-wide default binning


class Density2DChartResponseSchema(ChartResponseSchema[Density2DChartDataSchema]):
    config: Density2DChartConfigSchema | None = None
