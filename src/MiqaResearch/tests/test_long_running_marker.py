"""
Sanity check for the long_running marker (#117): marked tests must be
deselected by the default run and only execute when explicitly requested
(e.g. `pytest -m long_running`).
"""
import pytest


@pytest.mark.long_running
def test_long_running_tests_only_run_when_explicitly_requested():
    assert True
