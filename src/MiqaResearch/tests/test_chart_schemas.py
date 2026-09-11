import pytest
from ninja import Schema
from pydantic import ValidationError

from MiqaResearch.data.serializers.charts.bar import (
    BarChartDataSchema,
    BarChartResponseSchema,
    BarSeriesSchema,
)
from MiqaResearch.data.serializers.charts.base import ChartResponseSchema
from MiqaResearch.data.serializers.charts.box import (
    BoxChartConfigSchema,
    BoxChartDataSchema,
    BoxChartResponseSchema,
    BoxEntrySchema,
    BoxStatsSchema,
)
from MiqaResearch.data.serializers.charts.density_2d import (
    Density2DBinsSchema,
    Density2DChartConfigSchema,
    Density2DChartDataSchema,
    Density2DChartResponseSchema,
    Density2DSeriesSchema,
)
from MiqaResearch.data.serializers.charts.heatmap import (
    HeatmapChartConfigSchema,
    HeatmapChartDataSchema,
    HeatmapChartResponseSchema,
)
from MiqaResearch.data.serializers.charts.histogram import (
    HistogramBinsSchema,
    HistogramChartDataSchema,
    HistogramChartResponseSchema,
    HistogramSeriesSchema,
)
from MiqaResearch.data.serializers.charts.pie import (
    PieChartConfigSchema,
    PieChartDataSchema,
    PieChartResponseSchema,
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


def test_pie_chart_data_schema_is_flat_with_no_series_wrapper():
    data = PieChartDataSchema.model_validate({"labels": ["A", "B", "C"], "values": [4, 9, 2]})

    assert data.labels == ["A", "B", "C"]
    assert data.values == [4.0, 9.0, 2.0]


def test_pie_chart_config_schema_defaults_to_none():
    payload = {
        "config": {},
        "groupings": [
            {"name": "only", "label": "Only", "data": {"labels": [], "values": []}},
        ],
    }

    parsed = PieChartResponseSchema.model_validate(payload)

    assert parsed.config.hole is None
    assert parsed.config.sort is None
    assert parsed.config.textinfo is None


def test_pie_chart_config_schema_accepts_hole_within_bounds():
    payload = {
        "config": {"hole": 0.6},
        "groupings": [
            {"name": "only", "label": "Only", "data": {"labels": [], "values": []}},
        ],
    }

    parsed = PieChartResponseSchema.model_validate(payload)

    assert parsed.config.hole == 0.6


@pytest.mark.parametrize("hole", [-0.1, 1.1])
def test_pie_chart_config_schema_rejects_hole_outside_0_to_1(hole):
    with pytest.raises(ValidationError):
        PieChartConfigSchema.model_validate({"hole": hole})


def test_pie_chart_config_schema_respects_sort_and_textinfo():
    payload = {
        "config": {"sort": False, "textinfo": "value+percent"},
        "groupings": [
            {"name": "only", "label": "Only", "data": {"labels": [], "values": []}},
        ],
    }

    parsed = PieChartResponseSchema.model_validate(payload)

    assert parsed.config.sort is False
    assert parsed.config.textinfo == "value+percent"


def test_pie_chart_response_schema_validates_plain_pie_payload():
    payload = {
        "groupings": [
            {
                "name": "by_site",
                "label": "By Site",
                "data": {"labels": ["A", "B"], "values": [4, 9]},
            }
        ],
    }

    parsed = PieChartResponseSchema.model_validate(payload)

    assert parsed.config is None
    assert parsed.groupings[0].data.labels == ["A", "B"]


def test_pie_chart_response_schema_validates_donut_payload():
    payload = {
        "config": {"hole": 0.5, "sort": False, "textinfo": "label"},
        "groupings": [
            {
                "name": "by_site",
                "label": "By Site",
                "data": {"labels": ["A", "B"], "values": [4, 9]},
            }
        ],
    }

    parsed = PieChartResponseSchema.model_validate(payload)

    assert parsed.config.hole == 0.5
    assert parsed.config.sort is False
    assert parsed.config.textinfo == "label"


def test_pie_chart_response_schema_config_is_optional():
    payload = {
        "groupings": [
            {"name": "only", "label": "Only", "data": {"labels": [], "values": []}},
        ],
    }

    parsed = PieChartResponseSchema.model_validate(payload)

    assert parsed.config is None


def test_pie_chart_response_schema_json_schema_generation_does_not_error():
    schema = PieChartResponseSchema.model_json_schema()

    assert "properties" in schema
    assert "groupings" in schema["properties"]


def test_box_stats_schema_validates_optional_fields_default_to_none():
    stats = BoxStatsSchema.model_validate({"q1": 1, "median": 2, "q3": 3})

    assert stats.lower_fence is None
    assert stats.upper_fence is None
    assert stats.mean is None
    assert stats.sd is None


def test_box_entry_schema_requires_exactly_one_of_values_or_stats():
    with pytest.raises(ValidationError):
        BoxEntrySchema.model_validate({"name": "A"})


def test_box_entry_schema_rejects_both_values_and_stats():
    with pytest.raises(ValidationError):
        BoxEntrySchema.model_validate(
            {"name": "A", "values": [1, 2, 3], "stats": {"q1": 1, "median": 2, "q3": 3}}
        )


def test_box_entry_schema_accepts_raw_values_only():
    entry = BoxEntrySchema.model_validate({"name": "A", "values": [1, 2, 3]})

    assert entry.values == [1.0, 2.0, 3.0]
    assert entry.stats is None


def test_box_entry_schema_accepts_precomputed_stats_only():
    entry = BoxEntrySchema.model_validate(
        {"name": "A", "stats": {"q1": 1, "median": 2, "q3": 3, "lower_fence": 0, "upper_fence": 4}}
    )

    assert entry.values is None
    assert entry.stats.q1 == 1.0
    assert entry.stats.lower_fence == 0.0


def test_box_chart_data_schema_supports_a_flat_list_of_named_boxes_with_raw_values():
    data = BoxChartDataSchema.model_validate(
        {
            "boxes": [
                {"name": "A", "values": [1, 2, 3]},
                {"name": "B", "values": [4, 5]},
            ]
        }
    )

    assert len(data.boxes) == 2
    assert data.boxes[0].name == "A"
    assert data.boxes[0].group is None


def test_box_chart_data_schema_supports_a_grouped_multi_dimension_case():
    data = BoxChartDataSchema.model_validate(
        {
            "boxes": [
                {"name": "Q1", "group": "Site A", "values": [1, 2]},
                {"name": "Q1", "group": "Site B", "values": [3, 4]},
            ]
        }
    )

    assert data.boxes[0].group == "Site A"
    assert data.boxes[1].group == "Site B"


def test_box_chart_data_schema_supports_precomputed_stats():
    data = BoxChartDataSchema.model_validate(
        {
            "boxes": [
                {"name": "A", "stats": {"q1": 1, "median": 2, "q3": 3}},
            ]
        }
    )

    assert data.boxes[0].stats.median == 2.0
    assert data.boxes[0].values is None


def test_box_chart_config_schema_defaults_to_none():
    payload = {
        "config": {},
        "groupings": [
            {"name": "only", "label": "Only", "data": {"boxes": []}},
        ],
    }

    parsed = BoxChartResponseSchema.model_validate(payload)

    assert parsed.config.quartile_method is None
    assert parsed.config.orientation is None


def test_box_chart_config_schema_respects_quartile_method_and_orientation():
    payload = {
        "config": {"quartile_method": "inclusive", "orientation": "h"},
        "groupings": [
            {"name": "only", "label": "Only", "data": {"boxes": []}},
        ],
    }

    parsed = BoxChartResponseSchema.model_validate(payload)

    assert parsed.config.quartile_method == "inclusive"
    assert parsed.config.orientation == "h"


def test_box_chart_response_schema_config_is_optional():
    payload = {
        "groupings": [
            {"name": "only", "label": "Only", "data": {"boxes": []}},
        ],
    }

    parsed = BoxChartResponseSchema.model_validate(payload)

    assert parsed.config is None


def test_box_chart_response_schema_validates_full_payload_with_mixed_entries():
    payload = {
        "config": {"quartile_method": "exclusive", "orientation": "v"},
        "groupings": [
            {
                "name": "by_site",
                "label": "By Site",
                "data": {
                    "boxes": [
                        {"name": "A", "group": "Site A", "values": [1, 2, 3]},
                        {"name": "B", "group": "Site B", "stats": {"q1": 1, "median": 2, "q3": 3}},
                    ]
                },
            }
        ],
    }

    parsed = BoxChartResponseSchema.model_validate(payload)

    assert parsed.config.quartile_method == "exclusive"
    assert parsed.groupings[0].data.boxes[0].values == [1.0, 2.0, 3.0]
    assert parsed.groupings[0].data.boxes[1].stats.median == 2.0


def test_box_chart_response_schema_json_schema_generation_does_not_error():
    schema = BoxChartResponseSchema.model_json_schema()

    assert "properties" in schema
    assert "groupings" in schema["properties"]


def test_box_chart_config_schema_rejects_invalid_quartile_method():
    with pytest.raises(ValidationError):
        BoxChartConfigSchema.model_validate({"quartile_method": "median"})


def test_heatmap_chart_data_schema_validates_a_z_matrix_with_no_axis_labels():
    data = HeatmapChartDataSchema.model_validate({"z": [[1, 2], [3, 4]]})

    assert data.z == [[1.0, 2.0], [3.0, 4.0]]
    assert data.x is None
    assert data.y is None


def test_heatmap_chart_data_schema_accepts_explicit_x_and_y_labels():
    data = HeatmapChartDataSchema.model_validate(
        {"z": [[1, 2]], "x": ["a", "b"], "y": ["row1"]}
    )

    assert data.x == ["a", "b"]
    assert data.y == ["row1"]


def test_heatmap_chart_config_schema_defaults_to_none():
    payload = {
        "config": {},
        "groupings": [{"name": "only", "label": "Only", "data": {"z": [[1]]}}],
    }

    parsed = HeatmapChartResponseSchema.model_validate(payload)

    assert parsed.config.color_scale is None
    assert parsed.config.z_mid is None


def test_heatmap_chart_config_schema_respects_color_scale_and_z_mid():
    payload = {
        "config": {"color_scale": "diverging", "z_mid": 5},
        "groupings": [{"name": "only", "label": "Only", "data": {"z": [[-1, 1]]}}],
    }

    parsed = HeatmapChartResponseSchema.model_validate(payload)

    assert parsed.config.color_scale == "diverging"
    assert parsed.config.z_mid == 5.0


def test_heatmap_chart_config_schema_rejects_invalid_color_scale():
    with pytest.raises(ValidationError):
        HeatmapChartConfigSchema.model_validate({"color_scale": "invalid"})


def test_heatmap_chart_response_schema_config_is_optional():
    payload = {
        "groupings": [{"name": "only", "label": "Only", "data": {"z": [[1]]}}],
    }

    parsed = HeatmapChartResponseSchema.model_validate(payload)

    assert parsed.config is None


def test_heatmap_chart_response_schema_validates_full_payload():
    payload = {
        "config": {"color_scale": "sequential"},
        "groupings": [
            {
                "name": "correlation",
                "label": "Correlation",
                "data": {"z": [[1, 0.5], [0.5, 1]], "x": ["A", "B"], "y": ["A", "B"]},
            }
        ],
    }

    parsed = HeatmapChartResponseSchema.model_validate(payload)

    assert parsed.config.color_scale == "sequential"
    assert parsed.groupings[0].data.z == [[1.0, 0.5], [0.5, 1.0]]
    assert parsed.groupings[0].data.x == ["A", "B"]


def test_heatmap_chart_response_schema_json_schema_generation_does_not_error():
    schema = HeatmapChartResponseSchema.model_json_schema()

    assert "properties" in schema
    assert "groupings" in schema["properties"]


def test_density_2d_series_schema_optional_fields_default_to_none():
    series = Density2DSeriesSchema(name="All", x=[1.0, 2.0], y=[3.0, 4.0])

    assert series.bins is None


def test_density_2d_bins_schema_validates_all_fields():
    bins = Density2DBinsSchema.model_validate(
        {"nbinsx": 10, "nbinsy": 20, "xbins": {"start": 0, "end": 100, "size": 10}}
    )

    assert bins.nbinsx == 10
    assert bins.nbinsy == 20
    assert bins.xbins == {"start": 0, "end": 100, "size": 10}


def test_density_2d_chart_data_schema_supports_a_single_series_with_no_bins():
    data = Density2DChartDataSchema.model_validate(
        {"series": [{"name": "All", "x": [1, 2, 3], "y": [4, 5, 6]}]}
    )

    assert len(data.series) == 1
    assert data.series[0].bins is None


def test_density_2d_chart_data_schema_supports_multiple_overlaid_series():
    data = Density2DChartDataSchema.model_validate(
        {
            "series": [
                {"name": "Site A", "x": [1, 2], "y": [1, 2]},
                {"name": "Site B", "x": [3, 4], "y": [3, 4]},
            ]
        }
    )

    assert len(data.series) == 2
    assert data.series[1].name == "Site B"


def test_density_2d_chart_data_schema_supports_per_series_bins_override():
    data = Density2DChartDataSchema.model_validate(
        {
            "series": [
                {"name": "Site A", "x": [1, 2], "y": [1, 2], "bins": {"nbinsx": 5}},
                {"name": "Site B", "x": [3, 4], "y": [3, 4]},
            ]
        }
    )

    assert data.series[0].bins.nbinsx == 5
    assert data.series[1].bins is None


def test_density_2d_chart_config_schema_defaults_to_none():
    payload = {
        "config": {},
        "groupings": [{"name": "only", "label": "Only", "data": {"series": []}}],
    }

    parsed = Density2DChartResponseSchema.model_validate(payload)

    assert parsed.config.style is None
    assert parsed.config.density_bins is None


def test_density_2d_chart_config_schema_respects_style_and_density_bins():
    payload = {
        "config": {"style": "contour", "density_bins": {"nbinsx": 20, "nbinsy": 20}},
        "groupings": [{"name": "only", "label": "Only", "data": {"series": []}}],
    }

    parsed = Density2DChartResponseSchema.model_validate(payload)

    assert parsed.config.style == "contour"
    assert parsed.config.density_bins.nbinsx == 20


def test_density_2d_chart_config_schema_rejects_invalid_style():
    with pytest.raises(ValidationError):
        Density2DChartConfigSchema.model_validate({"style": "invalid"})


def test_density_2d_chart_response_schema_config_is_optional():
    payload = {
        "groupings": [{"name": "only", "label": "Only", "data": {"series": []}}],
    }

    parsed = Density2DChartResponseSchema.model_validate(payload)

    assert parsed.config is None


def test_density_2d_chart_response_schema_validates_full_payload_for_both_styles():
    for style in ("heatmap", "contour"):
        payload = {
            "config": {"style": style},
            "groupings": [
                {
                    "name": "by_site",
                    "label": "By Site",
                    "data": {"series": [{"name": "All", "x": [1, 2], "y": [3, 4]}]},
                }
            ],
        }

        parsed = Density2DChartResponseSchema.model_validate(payload)

        assert parsed.config.style == style
        assert parsed.groupings[0].data.series[0].x == [1.0, 2.0]


def test_density_2d_chart_response_schema_json_schema_generation_does_not_error():
    schema = Density2DChartResponseSchema.model_json_schema()

    assert "properties" in schema
    assert "groupings" in schema["properties"]
