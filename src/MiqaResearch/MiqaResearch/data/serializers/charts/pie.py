from typing import Literal

from ninja import Schema
from pydantic import Field

from MiqaResearch.data.serializers.charts.base import ChartConfigSchema, ChartResponseSchema


class PieChartDataSchema(Schema):
    labels: list[str]  # FLAT — no `series` wrapper; a pie has exactly one distribution per Grouping
    values: list[float]


class PieChartConfigSchema(ChartConfigSchema):
    hole: float | None = Field(default=None, ge=0, le=1)  # 0 (default) = plain pie; 0.4-0.7 = donut
    sort: bool | None = None  # default true (plotly's own default); false preserves array order
    textinfo: (
        Literal[
            "label",
            "value",
            "percent",
            "label+percent",
            "label+value",
            "value+percent",
            "label+value+percent",
            "none",
        ]
        | None
    ) = None


class PieChartResponseSchema(ChartResponseSchema[PieChartDataSchema]):
    config: PieChartConfigSchema | None = None
