import pytest
from django.core.cache import cache


@pytest.fixture(autouse=True)
def _settings_and_cache():
    cache.clear()
    yield
    cache.clear()
