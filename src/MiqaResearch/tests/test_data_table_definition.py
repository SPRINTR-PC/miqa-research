import pytest
from ninja.errors import HttpError

from MiqaResearch.data.serializers.data_table_definition import DataTableColumn, DataTableDefinition


def _definition(**overrides):
    columns = (
        DataTableColumn("name", "Name", "string", sortable=True),
        DataTableColumn("age", "Age", "number", sortable=True),
        DataTableColumn("secret", "Secret", "string", sortable=False),
    )
    return DataTableDefinition(columns=overrides.pop("columns", columns), **overrides)


def test_no_sort_and_no_declared_default_falls_back_to_descending_primary_key():
    assert _definition().ordering_for(None) == ["-pk"]


def test_blank_sort_is_treated_as_no_sort():
    assert _definition().ordering_for("") == ["-pk"]


def test_declared_defaults_are_ordered_by_default_sort_order_and_get_a_pk_tiebreaker():
    definition = _definition(columns=(
        DataTableColumn("name", "Name", "string", sortable=True, default_sort="asc", default_sort_order=2),
        DataTableColumn("age", "Age", "number", sortable=True, default_sort="desc", default_sort_order=1),
    ))

    assert definition.ordering_for(None) == ["-age", "name", "pk"]


def test_requested_sort_keeps_direction_and_order_and_appends_pk_tiebreaker():
    assert _definition().ordering_for("-age,name") == ["-age", "name", "pk"]


def test_requested_sort_replaces_the_default():
    definition = _definition(columns=(
        DataTableColumn("name", "Name", "string", sortable=True, default_sort="asc", default_sort_order=1),
        DataTableColumn("age", "Age", "number", sortable=True),
    ))

    assert definition.ordering_for("age") == ["age", "pk"]


def test_sorting_by_the_primary_key_explicitly_does_not_add_a_second_tiebreaker():
    definition = _definition(columns=(DataTableColumn("pk", "Id", "number", sortable=True),))

    assert definition.ordering_for("-pk") == ["-pk"]


@pytest.mark.parametrize("sort", ["nope", "name,nope", "-nope"])
def test_unknown_sort_column_is_a_400(sort):
    with pytest.raises(HttpError) as error:
        _definition().ordering_for(sort)

    assert error.value.status_code == 400


def test_non_sortable_sort_column_is_a_400():
    with pytest.raises(HttpError) as error:
        _definition().ordering_for("secret")

    assert error.value.status_code == 400


def test_six_sort_columns_are_allowed_and_seven_are_a_400():
    columns = tuple(DataTableColumn(f"c{i}", f"C{i}", "string", sortable=True) for i in range(7))
    definition = _definition(columns=columns)

    assert definition.ordering_for(",".join(f"c{i}" for i in range(6))) == [f"c{i}" for i in range(6)] + ["pk"]
    with pytest.raises(HttpError) as error:
        definition.ordering_for(",".join(f"c{i}" for i in range(7)))
    assert error.value.status_code == 400


@pytest.mark.parametrize("sort", ["name,,age", ",name", "name,", ",,"])
def test_empty_sort_tokens_are_a_400_rather_than_silently_ignored(sort):
    with pytest.raises(HttpError) as error:
        _definition().ordering_for(sort)

    assert error.value.status_code == 400


@pytest.mark.parametrize("sort", ["name,name", "name,-name"])
def test_sorting_by_the_same_column_twice_is_a_400(sort):
    with pytest.raises(HttpError) as error:
        _definition().ordering_for(sort)

    assert error.value.status_code == 400
