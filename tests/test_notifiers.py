import types

import pytest

import mylar
from mylar import notifiers


class FakeResponse:
    def __init__(self, status_code, text=''):
        self.status_code = status_code
        self.text = text


@pytest.mark.unit
@pytest.mark.parametrize('status,expected', [(204, True), (200, True), (400, False), (404, False)])
def test_discord_test_notify_status(monkeypatch, status, expected):
    monkeypatch.setattr(mylar, 'CONFIG', types.SimpleNamespace(DISCORD_WEBHOOK_URL=None), raising=False)
    monkeypatch.setattr(notifiers.requests, 'post', lambda *a, **k: FakeResponse(status, 'body'))
    assert notifiers.DISCORD(test_webhook_url='https://discord.invalid/api/webhooks/1/x').test_notify() is expected


@pytest.mark.unit
def test_discord_request_error(monkeypatch):
    monkeypatch.setattr(mylar, 'CONFIG', types.SimpleNamespace(DISCORD_WEBHOOK_URL=None), raising=False)

    def boom(*a, **k):
        raise ConnectionError('nope')
    monkeypatch.setattr(notifiers.requests, 'post', boom)
    assert notifiers.DISCORD(test_webhook_url='https://discord.invalid/api/webhooks/1/x').test_notify() is False
