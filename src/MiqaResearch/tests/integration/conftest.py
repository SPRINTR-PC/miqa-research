from pathlib import Path

import pytest

@pytest.fixture(scope="session")
def example_data_main_dir():
    return Path(__file__).resolve().parent.parent / "example_data"
