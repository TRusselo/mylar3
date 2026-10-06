import types

import pytest

import mylar
from mylar import config, search


@pytest.fixture(autouse=True)
def cfg(monkeypatch):
    monkeypatch.setattr(mylar, 'CONFIG', types.SimpleNamespace(**{k: v[2] for k, v in config._CONFIG_DEFINITIONS.items()}), raising=False)


@pytest.mark.unit
@pytest.mark.parametrize('name,issue,expected', [
    ('X-Men Annual', '1', False),
    ('Ghost Rider Annual', '1', False),
    ('X-Men Annual', '7', False),
    ('X-Men 2021 Annual', '1', True),
    ('Action Comics 2022 Annual', '1', True),
    ('Batman Annual', None, True),
    ('Batman', '1', False),
])
def test_annual_as_oneshot(name, issue, expected):
    assert search.annual_as_oneshot(name, issue) is expected
