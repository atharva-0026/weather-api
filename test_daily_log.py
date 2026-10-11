"""Behaviour of daily_log.fetch_stats retries (no network: requests.get is stubbed)."""
import requests

import daily_log


class _Resp:
    def __init__(self, status, payload=None, text=""):
        self.status_code = status
        self._payload = payload
        self.text = text

    def json(self):
        return self._payload


def _stub(monkeypatch, responses):
    calls = []

    def fake_get(url, timeout):
        calls.append(url)
        r = responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r

    monkeypatch.setattr(daily_log.requests, "get", fake_get)
    return calls


def test_retries_5xx_until_success(monkeypatch):
    calls = _stub(monkeypatch, [_Resp(503, text="waking up"), _Resp(503), _Resp(200, {"temp": 24})])
    slept = []
    data = daily_log.fetch_stats(sleep=slept.append)
    assert data["pune_weather"] == {"temp": 24}
    assert len(calls) == 3 and slept == [20, 40]


def test_retries_connection_errors(monkeypatch):
    _stub(monkeypatch, [requests.ConnectionError("reset"), _Resp(200, {"ok": 1})])
    assert daily_log.fetch_stats(sleep=lambda s: None)["pune_weather"] == {"ok": 1}


def test_gives_up_after_all_attempts_and_keeps_error_detail(monkeypatch):
    calls = _stub(monkeypatch, [_Resp(503, text="Service Unavailable")] * 4)
    slept = []
    data = daily_log.fetch_stats(sleep=slept.append)
    assert data["pune_weather"]["error"] == 503
    assert data["pune_weather"]["detail"] == "Service Unavailable"
    assert len(calls) == 4 and slept == [20, 40, 60]


def test_does_not_retry_4xx(monkeypatch):
    calls = _stub(monkeypatch, [_Resp(404, text="Not Found")])
    slept = []
    data = daily_log.fetch_stats(sleep=slept.append)
    assert data["pune_weather"]["error"] == 404
    assert len(calls) == 1 and slept == []
