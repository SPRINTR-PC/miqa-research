from typing import Generic, Literal, TypeVar

from ninja import Schema

TData = TypeVar("TData")


class ChartEventCallbacksSchema(Schema):
    """Names of the registered Chart Event Callbacks a chart invokes on click/zoom."""

    click: str | None = None
    zoom: str | None = None


class ChartConfigSchema(Schema):
    """Chart Config: layout/behaviour settings fixed across every Grouping in a response."""

    webgl_threshold: int | None = None
    force_renderer: Literal["svg", "webgl", "auto"] | None = None
    event_callbacks: ChartEventCallbacksSchema | None = None
    subplot: dict | None = None  # only meaningful on the Chart Grid response


class ChartGroupingLabelsSchema(Schema):
    x_axis_title: str | None = None
    y_axis_title: str | None = None
    legend_title: str | None = None
    # Either element may be None to pin just that end while the other stays
    # autoranged (native Plotly `range` behaviour).
    x_axis_range: tuple[float | None, float | None] | None = None
    y_axis_range: tuple[float | None, float | None] | None = None


class ChartGroupingSchema(Schema, Generic[TData]):
    """One Chart Grouping: a named alternative view of the same underlying dataset."""

    name: str
    label: str
    labels: ChartGroupingLabelsSchema | None = None
    data: TData


class ChartResponseSchema(Schema, Generic[TData]):
    """The full response shape returned by a chart component's dataUrl endpoint.

    `groupings` is always a non-empty list, even when there is only one Chart
    Grouping — the component skips rendering the dropdown at length 1 rather
    than the API using a distinct single-Grouping shape.
    """

    config: ChartConfigSchema | None = None
    groupings: list[ChartGroupingSchema[TData]]
