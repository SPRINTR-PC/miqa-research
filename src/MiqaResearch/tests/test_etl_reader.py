"""Unit tests for the pure `location_grant_allows` helper backing the ETL binding wizard (#158):
a Binding's source bucket/prefix must fall within one of the project's `EtlLocationGrant`s.
"""
from types import SimpleNamespace

from MiqaResearch.readers.etl_reader import location_grant_allows


def _grant(bucket, prefix=""):
    return SimpleNamespace(bucket=bucket, prefix=prefix)


def test_no_grants_allows_nothing():
    assert not location_grant_allows([], "incoming", "redcap/")


def test_an_empty_prefix_grant_covers_the_whole_bucket():
    grants = [_grant("incoming")]

    assert location_grant_allows(grants, "incoming", "redcap/")
    assert location_grant_allows(grants, "incoming", "")


def test_a_prefixed_grant_covers_only_matching_or_deeper_paths():
    grants = [_grant("incoming", "redcap/")]

    assert location_grant_allows(grants, "incoming", "redcap/")
    assert location_grant_allows(grants, "incoming", "redcap/2024/")
    assert not location_grant_allows(grants, "incoming", "other/")
    assert not location_grant_allows(grants, "incoming", "")


def test_grant_for_a_different_bucket_does_not_match():
    grants = [_grant("incoming", "redcap/")]

    assert not location_grant_allows(grants, "other-bucket", "redcap/")


def test_any_matching_grant_among_several_is_enough():
    grants = [_grant("a", "x/"), _grant("incoming", "redcap/")]

    assert location_grant_allows(grants, "incoming", "redcap/2024/")
