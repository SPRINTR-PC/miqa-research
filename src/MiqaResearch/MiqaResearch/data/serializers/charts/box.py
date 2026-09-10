from typing import Literal

from ninja import Schema
from pydantic import model_validator

from MiqaResearch.data.serializers.charts.base import ChartConfigSchema, ChartResponseSchema


class BoxStatsSchema(Schema):
    q1: float
    median: float
    q3: float
    lower_fence: float | None = None
    upper_fence: float | None = None
    mean: float | None = None
    sd: float | None = None


class BoxEntrySchema(Schema):
    name: str
    group: str | None = None  # boxes sharing a group become one trace (boxmode: "group")
    values: list[float] | None = None  # raw values — default
    stats: BoxStatsSchema | None = None  # precomputed alternative to `values`

    @model_validator(mode="after")
    def exactly_one_of_values_or_stats(self):
        if bool(self.values) == bool(self.stats):
            raise ValueError("Exactly one of `values` or `stats` is required.")
        return self


class BoxChartDataSchema(Schema):
    boxes: list[BoxEntrySchema]


class BoxChartConfigSchema(ChartConfigSchema):
    quartile_method: Literal["linear", "exclusive", "inclusive"] | None = None
    orientation: Literal["v", "h"] | None = None


class BoxChartResponseSchema(ChartResponseSchema[BoxChartDataSchema]):
    config: BoxChartConfigSchema | None = None
