from typing import Literal

from ninja import Schema

from MiqaResearch.data.serializers.charts.base import ChartConfigSchema, ChartResponseSchema


class HistogramBinsSchema(Schema):
    nbinsx: int | None = None
    start: float | None = None
    end: float | None = None
    size: float | None = None


class HistogramSeriesSchema(Schema):
    name: str
    values: list[float]  # raw per-record values — no server-side pre-aggregation
    bins: HistogramBinsSchema | None = None  # overrides HistogramChartConfigSchema.histogram_bins


class HistogramChartDataSchema(Schema):
    series: list[HistogramSeriesSchema]


class HistogramChartConfigSchema(ChartConfigSchema):
    histogram_bins: HistogramBinsSchema | None = None  # chart-wide default binning
    orientation: Literal["v", "h"] | None = None  # default "v"
    histnorm: Literal["", "percent", "probability", "density", "probability density"] | None = None


class HistogramChartResponseSchema(ChartResponseSchema[HistogramChartDataSchema]):
    config: HistogramChartConfigSchema | None = None
