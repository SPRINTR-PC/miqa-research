from typing import Literal

from ninja import Schema

from MiqaResearch.data.serializers.charts.base import ChartConfigSchema, ChartResponseSchema


class SankeyNodeSchema(Schema):
    label: str
    color: str | None = None  # explicit override; defaults to a neutral tone when omitted


class SankeyLinkSchema(Schema):
    source: int
    target: int
    value: float
    color: str | None = None  # defaults to a translucent tint of the source node's color


class SankeyChartDataSchema(Schema):
    nodes: list[SankeyNodeSchema]
    links: list[SankeyLinkSchema]


class SankeyChartConfigSchema(ChartConfigSchema):
    orientation: Literal["h", "v"] | None = None  # default "h"
    arrangement: Literal["snap", "perpendicular", "freeform", "fixed"] | None = None  # default "snap"


class SankeyChartResponseSchema(ChartResponseSchema[SankeyChartDataSchema]):
    config: SankeyChartConfigSchema | None = None
