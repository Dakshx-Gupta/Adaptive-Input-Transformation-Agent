import pytest
from datetime import date
from adapter.context import Context


@pytest.fixture
def ctx():
    return Context(reference_date=date(2026, 10, 13), timezone="Asia/Kolkata")
