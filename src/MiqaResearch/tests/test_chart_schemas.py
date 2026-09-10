from ninja import Schema

from MiqaResearch.data.serializers.charts.bar import (
    BarChartDataSchema,
    BarChartResponseSchema,
    BarSeriesSchema,
)
from MiqaResearch.data.serializers.charts.base import ChartResponseSchema
from MiqaResearch.data.serializers.charts.histogram import (
    HistogramBinsSchema,
    HistogramChartDataSchema,
    HistogramChartResponseSchema,
    HistogramSeriesSchema,
)
from MiqaResearch.data.serializers.charts.xy import (
    LineChartResponseSchema,
    XYChartDataSchema,
    XYSeriesSchema,
)


def test_chart_response_schema_generic_resolves_for_xy_data():
    payload = {
        "config": {"webgl_threshold": 50},
        "groupings": [
            {
                "name": "by_site",
                "label": "By Site",
                "data": {
                    "series": [
                        {"name": "Site A", "x": [1, 2, 3], "y": [1.0, 2.0, 3.0]},
                    ]
                },
            }
        ],
    }

    parsed = LineChartResponseSchema.model_validate(payload)

    assert parsed.config.webgl_threshold == 50
    assert parsed.groupings[0].name == "by_site"
    assert parsed.groupings[0].data.series[0].name == "Site A"
    assert parsed.groupings[0].data.series[0].x == [1, 2, 3]


def test_chart_response_schema_groupings_is_always_a_list():
    payload = {
        "groupings": [
            {"name": "only", "label": "Only", "data": {"series": []}},
        ],
    }

    parsed = LineChartResponseSchema.model_validate(payload)

    assert len(parsed.groupings) == 1
    assert parsed.config is None


def test_chart_response_schema_labels_override_axis_and_legend_titles():
    payload = {
        "groupings": [
            {
                "name": "by_site",
                "label": "By Site",
                "labels": {"x_axis_title": "Site", "y_axis_title": "Count"},
                "data": {"series": []},
            }
        ],
    }

    parsed = LineChartResponseSchema.model_validate(payload)

    assert parsed.groupings[0].labels.x_axis_title == "Site"
    assert parsed.groupings[0].labels.y_axis_title == "Count"
    assert parsed.groupings[0].labels.legend_title is None


def test_chart_response_schema_json_schema_generation_does_not_error():
    schema = LineChartResponseSchema.model_json_schema()

    assert "properties" in schema
    assert "groupings" in schema["properties"]


def test_chart_response_schema_generic_is_reusable_across_data_types():
    class OtherDataSchema(Schema):
        value: int

    OtherResponseSchema = ChartResponseSchema[OtherDataSchema]
    parsed = OtherResponseSchema.model_validate(
        {"groupings": [{"name": "n", "label": "N", "data": {"value": 3}}]}
    )

    assert parsed.groupings[0].data.value == 3


def test_xy_series_schema_optional_fields_default_to_none():
    series = XYSeriesSchema(name="s", x=[1], y=[1.0])

    assert series.size is None
    assert series.fill is None


def test_xy_chart_data_schema_validates_bubble_size():
    data = XYChartDataSchema.model_validate(
        {"series": [{"name": "s", "x": [1, 2], "y": [1.0, 2.0], "size": [4.0, 8.0]}]}
    )

    assert data.series[0].size == [4.0, 8.0]


def test_xy_chart_data_schema_x_accepts_mixed_json_scalars():
    data = XYChartDataSchema.model_validate(
        {
            "series": [
                {"name": "s", "x": ["2024-01-01", "2024-01-02"], "y": [1.0, 2.0]},
            ]
        }
    )

    assert data.series[0].x == ["2024-01-01", "2024-01-02"]


def test_bar_series_schema_validates_values():
    series = BarSeriesSchema.model_validate({"name": "Site A", "values": [1, 2, 3]})

    assert series.name == "Site A"
    assert series.values == [1.0, 2.0, 3.0]


def test_bar_chart_data_schema_supports_single_series():
    data = BarChartDataSchema.model_validate(
        {"categories": ["A", "B"], "series": [{"name": "Consents", "values": [4, 9]}]}
    )

    assert data.categories == ["A", "B"]
    assert len(data.series) == 1


def test_bar_chart_data_schema_supports_multiple_series():
    data = BarChartDataSchema.model_validate(
        {
            "categories": ["A", "B"],
            "series": [
                {"name": "Site A", "values": [1, 2]},
                {"name": "Site B", "values": [3, 4]},
            ],
        }
    )

    assert len(data.series) == 2
    assert data.series[1].name == "Site B"


def test_bar_chart_response_schema_validates_full_payload():
    payload = {
        "config": {"bar_mode": "stack", "orientation": "h"},
        "groupings": [
            {
                "name": "by_site",
                "label": "By Site",
                "data": {
                    "categories": ["A", "B"],
                    "series": [{"name": "Site A", "values": [1, 2]}],
                },
            }
        ],
    }

    parsed = BarChartResponseSchema.model_validate(payload)

    assert parsed.config.bar_mode == "stack"
    assert parsed.config.orientation == "h"
    assert parsed.groupings[0].data.categories == ["A", "B"]


def test_bar_chart_response_schema_config_is_optional():
    payload = {
        "groupings": [
            {"name": "only", "label": "Only", "data": {"categories": [], "series": []}},
        ],
    }

    parsed = BarChartResponseSchema.model_validate(payload)

    assert parsed.config is None


def test_bar_chart_config_schema_bar_mode_and_orientation_default_to_none():
    payload = {
        "groupings": [
            {
                "name": "only",
                "label": "Only",
                "data": {"categories": ["A"], "series": [{"name": "S", "values": [1]}]},
            }
        ],
        "config": {},
    }

    parsed = BarChartResponseSchema.model_validate(payload)

    assert parsed.config.bar_mode is None
    assert parsed.config.orientation is None


def test_bar_chart_response_schema_json_schema_generation_does_not_error():
    schema = BarChartResponseSchema.model_json_schema()

    assert "properties" in schema
    assert "groupings" in schema["properties"]


def test_histogram_series_schema_optional_fields_default_to_none():
    series = HistogramSeriesSchema(name="s", values=[1.0, 2.0, 3.0])

    assert series.bins is None


def test_histogram_bins_schema_validates_all_fields():
    bins = HistogramBinsSchema.model_validate({"nbinsx": 10, "start": 0, "end": 100, "size": 10})

    assert bins.nbinsx == 10
    assert bins.start == 0
    assert bins.end == 100
    assert bins.size == 10


def test_histogram_chart_data_schema_supports_single_series_with_no_bins():
    data = HistogramChartDataSchema.model_validate(
        {"series": [{"name": "Ages", "values": [1, 2, 2, 3, 3, 3]}]}
    )

    assert len(data.series) == 1
    assert data.series[0].bins is None


def test_histogram_chart_data_schema_supports_per_series_bins_override():
    data = HistogramChartDataSchema.model_validate(
        {
            "series": [
                {"name": "Ages", "values": [1, 2, 3], "bins": {"nbinsx": 5}},
                {"name": "Weights", "values": [10, 20, 30]},
            ]
        }
    )

    assert data.series[0].bins.nbinsx == 5
    assert data.series[1].bins is None


def test_histogram_chart_response_schema_validates_chart_wide_default_binning():
    payload = {
        "config": {"histogram_bins": {"nbinsx": 20}},
        "groupings": [
            {
                "name": "by_site",
                "label": "By Site",
                "data": {"series": [{"name": "Ages", "values": [1, 2, 3]}]},
            }
        ],
    }

    parsed = HistogramChartResponseSchema.model_validate(payload)

    assert parsed.config.histogram_bins.nbinsx == 20
    assert parsed.groupings[0].data.series[0].bins is None


def test_histogram_chart_response_schema_per_series_bins_override_chart_wide_default():
    payload = {
        "config": {"histogram_bins": {"nbinsx": 20}},
        "groupings": [
            {
                "name": "by_site",
                "label": "By Site",
                "data": {
                    "series": [
                        {"name": "Ages", "values": [1, 2, 3], "bins": {"nbinsx": 5}},
                    ]
                },
            }
        ],
    }

    parsed = HistogramChartResponseSchema.model_validate(payload)

    assert parsed.config.histogram_bins.nbinsx == 20
    assert parsed.groupings[0].data.series[0].bins.nbinsx == 5


def test_histogram_chart_config_schema_respects_histnorm():
    payload = {
        "config": {"histnorm": "percent"},
        "groupings": [
            {"name": "only", "label": "Only", "data": {"series": []}},
        ],
    }

    parsed = HistogramChartResponseSchema.model_validate(payload)

    assert parsed.config.histnorm == "percent"


def test_histogram_chart_config_schema_defaults_to_none():
    payload = {
        "config": {},
        "groupings": [
            {"name": "only", "label": "Only", "data": {"series": []}},
        ],
    }

    parsed = HistogramChartResponseSchema.model_validate(payload)

    assert parsed.config.histogram_bins is None
    assert parsed.config.orientation is None
    assert parsed.config.histnorm is None


def test_histogram_chart_response_schema_config_is_optional():
    payload = {
        "groupings": [
            {"name": "only", "label": "Only", "data": {"series": []}},
        ],
    }

    parsed = HistogramChartResponseSchema.model_validate(payload)

    assert parsed.config is None


def test_histogram_chart_response_schema_supports_both_orientations():
    for orientation in ("v", "h"):
        payload = {
            "config": {"orientation": orientation},
            "groupings": [
                {"name": "only", "label": "Only", "data": {"series": [{"name": "S", "values": [1]}]}},
            ],
        }

        parsed = HistogramChartResponseSchema.model_validate(payload)

        assert parsed.config.orientation == orientation


def test_histogram_chart_response_schema_json_schema_generation_does_not_error():
    schema = HistogramChartResponseSchema.model_json_schema()

    assert "properties" in schema
    assert "groupings" in schema["properties"]
