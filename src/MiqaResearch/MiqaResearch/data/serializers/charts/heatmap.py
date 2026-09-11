from typing import Literal

from ninja import Schema

from MiqaResearch.data.serializers.charts.base import ChartConfigSchema, ChartResponseSchema


class HeatmapChartDataSchema(Schema):
    z: list[list[float]]
    x: list[int | float | str] | None = None  # defaults to indices when omitted
    y: list[int | float | str] | None = None


class HeatmapChartConfigSchema(ChartConfigSchema):
    color_scale: Literal["sequential", "diverging"] | None = None  # default "sequential"
    z_mid: float | None = None  # only meaningful for "diverging" — default 0


class HeatmapChartResponseSchema(ChartResponseSchema[HeatmapChartDataSchema]):
    config: HeatmapChartConfigSchema | None = None
