from ninja import Schema

from MiqaResearch.data.serializers.charts.base import ChartConfigSchema, ChartResponseSchema


class ChartGridSubplotSpecSchema(Schema):
    """One subplot's fixed layout position — same for every Grouping. `type` matches
    a chart-type element's own `chartType` string (e.g. "bar", "filled-area")."""

    type: str
    row: int
    col: int
    config: dict | None = None


class ChartGridConfigSchema(ChartConfigSchema):
    rows: int
    cols: int
    subplots: list[ChartGridSubplotSpecSchema]


class ChartGridDataSchema(Schema):
    """One entry per subplot, same order as `ChartGridConfigSchema.subplots`.

    Each entry is validated loosely here; a view-level check can cross-validate
    entry i against the concrete DataSchema for config.subplots[i].type (e.g.
    BarChartDataSchema) if stricter validation is wanted.
    """

    subplots: list[dict]


class ChartGridResponseSchema(ChartResponseSchema[ChartGridDataSchema]):
    config: ChartGridConfigSchema | None = None
