from datetime import date
from decimal import Decimal

import pytest
from ninja.errors import HttpError

from MiqaResearch.data.serializers.data_table_definition import DataTableColumn, DataTableDefinition, DataTableFilter


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


# --- Filters ---------------------------------------------------------------------------------------------------


_STATUS_OPTIONS = (("signed", "Signed"), ("revoked", "Revoked"))


def _filterable():
    return DataTableDefinition(columns=(
        DataTableColumn("clinic__name", "Clinic", "string", filter=DataTableFilter("text")),
        DataTableColumn("exams", "Exams", "number", filter=DataTableFilter("numeric")),
        DataTableColumn("dose", "Dose", "number", filter=DataTableFilter("numeric-range")),
        DataTableColumn("signed_at", "Signed", "datetime", filter=DataTableFilter("date-range")),
        DataTableColumn("birthday", "Birthday", "date", filter=DataTableFilter("date-range")),
        DataTableColumn("state", "State", "string", filter=DataTableFilter("dropdown", _STATUS_OPTIONS)),
        DataTableColumn("states", "States", "string", filter=DataTableFilter("multi-select", _STATUS_OPTIONS)),
        DataTableColumn("active", "Active", "boolean", filter=DataTableFilter("boolean")),
        DataTableColumn("plain", "Plain", "string"),
    ))


@pytest.mark.parametrize("key, values, expected", [
    ("clinic__name__icontains", ["alp"], ("clinic__name__icontains", "alp")),
    ("exams", ["5"], ("exams", 5)),
    ("exams", ["5.5"], ("exams", Decimal("5.5"))),
    ("dose__gte", ["20"], ("dose__gte", 20)),
    ("dose__lte", ["80"], ("dose__lte", 80)),
    ("signed_at__gte", ["2026-02-03"], ("signed_at__date__gte", date(2026, 2, 3))),
    ("signed_at__lte", ["2026-02-05"], ("signed_at__date__lte", date(2026, 2, 5))),
    ("birthday__lte", ["2000-01-31"], ("birthday__lte", date(2000, 1, 31))),
    ("state", ["signed"], ("state", "signed")),
    ("states__in", ["signed,revoked"], ("states__in", ["signed", "revoked"])),
    ("active", ["true"], ("active", True)),
    ("active", ["False"], ("active", False)),
])
def test_filter_key_maps_to_the_lookup_derived_from_the_declared_filter_kind(key, values, expected):
    assert _filterable().filter_for(key, values) == expected


@pytest.mark.parametrize("key", [
    "nope", "plain", "plain__icontains", "clinic__name", "clinic__name__exact", "exams__gte", "dose", "dose__in",
    "state__in", "states", "active__icontains",
])
def test_undeclared_or_wrong_lookup_filter_keys_are_not_allowed(key):
    assert _filterable().filter_for(key, ["x"]) is None


@pytest.mark.parametrize("key, value", [
    ("exams", "abc"), ("exams", "nan"), ("dose__gte", ""), ("signed_at__gte", "yesterday"),
    ("signed_at__lte", "2026-13-40"), ("state", "unknown"), ("states__in", "signed,unknown"),
    ("states__in", "signed,,revoked"), ("active", "yes"),
    ("signed_at__gte", "20260205"), ("signed_at__gte", "2026-2-5"),  # only YYYY-MM-DD
    ("exams", "1e999999"), ("exams", "99999999999999999999999"), ("dose__lte", "-1e30"),  # would overflow the database
])
def test_values_that_cannot_be_coerced_are_a_400(key, value):
    with pytest.raises(HttpError) as error:
        _filterable().filter_for(key, [value])

    assert error.value.status_code == 400


def test_repeating_a_filter_key_is_a_400():
    with pytest.raises(HttpError) as error:
        _filterable().filter_for("clinic__name__icontains", ["a", "b"])

    assert error.value.status_code == 400


def test_column_metadata_carries_the_filter_kind_and_static_options():
    by_accessor = {column.accessor: column for column in _filterable().column_schemas}

    assert by_accessor["clinic__name"].filter.kind == "text"
    assert by_accessor["clinic__name"].filter.options is None
    assert [(o.value, o.label) for o in by_accessor["states"].filter.options] == [
        ("signed", "Signed"), ("revoked", "Revoked")]
    assert by_accessor["plain"].filter is None


# --- Exact text filters (optionally matched through a deterministic hash field) ---------------------------------------


def _exact():
    return DataTableDefinition(columns=(
        DataTableColumn("code", "Code", "string", filter=DataTableFilter("text-exact")),
        DataTableColumn(
            "person__pid", "PID", "string",
            filter=DataTableFilter("text-exact", hash_field="person__pid_hash")),
    ))


def test_exact_text_filter_is_a_case_sensitive_exact_match_on_the_column():
    assert _exact().filter_for("code", ["AbC"]) == ("code", "AbC")


def test_exact_text_filter_on_an_encrypted_column_matches_the_hash_field_with_the_deterministic_hash(settings):
    from helpers.db_fields import get_deterministic_hash

    settings.SENSITIVE_DATA_HASH_KEY = "unit-test-hash-key"

    assert _exact().filter_for("person__pid", ["19121212-0001"]) == (
        "person__pid_hash", get_deterministic_hash("19121212-0001"))


@pytest.mark.parametrize(
    "key", ["code__icontains", "code__exact", "code__in", "person__pid__icontains", "person__pid_hash"]
)
def test_exact_text_filter_allows_only_the_bare_column_key(key):
    assert _exact().filter_for(key, ["x"]) is None


def test_exact_text_filter_metadata_exposes_the_kind_but_not_the_hash_field():
    by_accessor = {column.accessor: column for column in _exact().column_schemas}

    assert by_accessor["person__pid"].filter.kind == "text-exact"
    assert "hash" not in by_accessor["person__pid"].model_dump_json()


def test_empty_exact_text_value_is_a_400_rather_than_matching_empty_rows():
    with pytest.raises(HttpError) as error:
        _exact().filter_for("code", [""])

    assert error.value.status_code == 400


def test_exact_filter_on_an_encrypted_column_is_a_clean_503_when_the_hash_key_is_not_configured(settings):
    settings.SENSITIVE_DATA_HASH_KEY = None

    with pytest.raises(HttpError) as error:
        _exact().filter_for("person__pid", ["19121212-0001"])

    assert error.value.status_code == 503
    assert "19121212" not in str(error.value.message)


def test_exact_text_filter_hashes_the_exact_string_without_normalising_it(settings):
    from helpers.db_fields import get_deterministic_hash

    settings.SENSITIVE_DATA_HASH_KEY = "unit-test-hash-key"

    assert _exact().filter_for("person__pid", [" Åsa "]) == ("person__pid_hash", get_deterministic_hash(" Åsa "))
