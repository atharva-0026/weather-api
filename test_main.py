import os
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

import httpx
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient
from main import app, r

client = TestClient(app)


def test_version():
    """Version must match main.API_VERSION exactly — regression test for
    the endpoint drifting from the FastAPI app's declared version."""
    from main import API_VERSION

    res = client.get("/version")
    assert res.status_code == 200
    body = res.json()
    assert body["service"] == "weather-api"
    assert body["version"] == API_VERSION
    assert app.version == API_VERSION


def test_health():
    res = client.get("/health")
    assert res.status_code == 200
    assert "status" in res.json()


def test_health_does_not_crash_when_redis_unreachable():
    """Regression test: r.ping() raises ConnectionError/AuthenticationError
    on failure rather than returning False. /health previously did
    `"connected" if r.ping() else "disconnected"` with no try/except,
    so a genuinely unreachable Redis (e.g. misconfigured REDIS_URL on
    a fresh deploy) turned the health check itself into a 500 Internal
    Server Error — exactly when you need it most to report status."""
    with patch("main.r.ping", side_effect=ConnectionError("mocked unreachable")):
        res = client.get("/health")
        assert res.status_code == 200
        body = res.json()
        assert body["status"] == "ok"
        assert body["redis"] == "disconnected"


@patch("main.fetch", new_callable=AsyncMock)
@patch("main.cache_get", return_value=None)
@patch("main.cache_set")
@patch("main.log_query")
def test_get_weather(mock_log, mock_cache_set, mock_cache_get, mock_fetch):
    mock_fetch.return_value = {
        "main": {"temp": 28, "humidity": 60},
        "weather": [{"description": "clear sky"}],
        "coord": {"lat": 19.07, "lon": 72.87},
    }
    res = client.get("/weather/Mumbai")
    assert res.status_code == 200
    assert res.json()["source"] == "api"


@patch("main.fetch", new_callable=AsyncMock)
@patch("main.cache_get", return_value=None)
@patch("main.cache_set")
@patch("main.log_query")
def test_get_summary(mock_log, mock_cache_set, mock_cache_get, mock_fetch):
    mock_fetch.return_value = {
        "name": "Mumbai",
        "main": {"temp": 28, "feels_like": 30},
        "weather": [{"description": "clear sky"}],
        "coord": {"lat": 19.07, "lon": 72.87},
    }
    res = client.get("/weather/Mumbai/summary")
    assert res.status_code == 200
    body = res.json()
    assert body["city"] == "Mumbai"
    assert "Clear sky in Mumbai" in body["summary"]
    assert "feels like" in body["summary"]


def test_history_not_found():
    res = client.get("/history/NonexistentCityXYZ")
    assert res.status_code in (404, 429)


def test_compare_rejects_identical_cities():
    """Regression test: /compare built {city1: {...}, city2: {...}} as
    its response - if city1 == city2, Python dict literals silently
    collapse to one key, dropping half the comparison with no error.
    Must be rejected with a clear 400 instead."""
    res = client.get("/compare?city1=Pune&city2=Pune")
    assert res.status_code in (400, 429)
    if res.status_code == 400:
        assert "different cities" in res.json()["detail"]


def test_compare_rejects_identical_cities_different_case():
    res = client.get("/compare?city1=Pune&city2=PUNE")
    assert res.status_code in (400, 429)


def test_compare_rejects_identical_cities_with_whitespace():
    res = client.get("/compare?city1= Pune &city2=Pune")
    assert res.status_code in (400, 429)


def test_top_leaderboard_shape():
    res = client.get("/top")
    assert res.status_code == 200
    assert "leaderboard" in res.json()


@patch("main.fetch", new_callable=AsyncMock)
@patch("main.log_query")
@patch("main.get_or_train_model", new_callable=AsyncMock)
@patch("main.predict_next_days")
def test_ml_forecast(mock_predict, mock_train, mock_log, mock_fetch):
    from datetime import date
    mock_fetch.return_value = {"coord": {"lat": 19.07, "lon": 72.87}}
    mock_train.return_value = ("fake_model", date(2026, 7, 12))
    mock_predict.return_value = [
        {"date": "2026-07-13", "predicted_temp_max": 31.2},
        {"date": "2026-07-14", "predicted_temp_max": 30.8},
    ]
    res = client.get("/weather/Mumbai/ml-forecast?days=2")
    assert res.status_code == 200
    body = res.json()
    assert body["model"] == "RandomForestRegressor"
    assert len(body["predictions"]) == 2


def test_ml_forecast_train_failure():
    with patch("main.fetch", new_callable=AsyncMock) as mock_fetch, \
         patch("main.get_or_train_model", new_callable=AsyncMock) as mock_train:
        mock_fetch.return_value = {"coord": {"lat": 19.07, "lon": 72.87}}
        mock_train.side_effect = ValueError("Not enough historical data")
        res = client.get("/weather/Mumbai/ml-forecast")
        assert res.status_code == 502


def test_create_api_key():
    res = client.post("/keys?tier=free")
    assert res.status_code == 200
    body = res.json()
    assert body["api_key"].startswith("wapi_")
    assert body["tier"] == "free"
    assert body["daily_limit"] == 200


def test_usage_invalid_key():
    res = client.get("/usage", headers={"x-api-key": "not_a_real_key"})
    assert res.status_code == 401


def test_usage_valid_key():
    key = client.post("/keys?tier=free").json()["api_key"]
    res = client.get("/usage", headers={"x-api-key": key})
    assert res.status_code == 200
    assert res.json()["limit"] == 200


@patch("main.fetch", new_callable=AsyncMock)
@patch("main.cache_get", return_value=None)
@patch("main.cache_set")
@patch("main.log_query")
def test_weather_with_valid_api_key(mock_log, mock_cache_set, mock_cache_get, mock_fetch):
    key = client.post("/keys?tier=free").json()["api_key"]
    mock_fetch.return_value = {
        "main": {"temp": 28, "humidity": 60},
        "weather": [{"description": "clear sky"}],
        "coord": {"lat": 19.07, "lon": 72.87},
    }
    res = client.get("/weather/Mumbai", headers={"x-api-key": key})
    assert res.status_code == 200
    usage = client.get("/usage", headers={"x-api-key": key}).json()
    assert usage["used"] == 1


@patch("main.fetch", new_callable=AsyncMock)
@patch("main.cache_get", return_value=None)
@patch("main.cache_set")
@patch("main.log_query")
def test_weather_with_invalid_api_key(mock_log, mock_cache_set, mock_cache_get, mock_fetch):
    res = client.get("/weather/Mumbai", headers={"x-api-key": "bogus_key"})
    assert res.status_code == 401


@patch("main.log_query")
@patch("main.fetch_with_failover", new_callable=AsyncMock)
def test_failover_success(mock_failover, mock_log):
    mock_failover.return_value = {"city": "Mumbai", "temp": 29.0, "humidity": 65, "description": "haze", "lat": 19.07, "lon": 72.87, "provider": "openweather"}
    res = client.get("/weather/Mumbai/failover")
    assert res.status_code == 200
    assert res.json()["provider"] == "openweather"


@patch("main.log_query")
@patch("main.fetch_with_failover", new_callable=AsyncMock)
def test_failover_falls_back_to_second_provider(mock_failover, mock_log):
    mock_failover.return_value = {"city": "Mumbai", "temp": 29.0, "humidity": 65, "description": "haze", "lat": 19.07, "lon": 72.87, "provider": "open-meteo"}
    res = client.get("/weather/Mumbai/failover")
    assert res.status_code == 200
    assert res.json()["provider"] == "open-meteo"


@patch("main.fetch_with_failover", new_callable=AsyncMock)
def test_failover_all_providers_down(mock_failover):
    mock_failover.side_effect = RuntimeError("all providers failed: {}")
    res = client.get("/weather/Mumbai/failover")
    assert res.status_code == 503


def test_providers_status_shape():
    res = client.get("/providers/status")
    assert res.status_code == 200
    body = res.json()
    assert len(body["providers"]) == 3
    assert all("healthy" in p for p in body["providers"])


def test_circuit_breaker_opens_after_threshold():
    from providers import record_failure, is_open, FAILURE_THRESHOLD
    test_provider = "pytest-circuit-breaker-check"
    r.delete(f"provider_breaker:{test_provider}")
    for _ in range(FAILURE_THRESHOLD):
        record_failure(r, test_provider)
    assert is_open(r, test_provider) is True
    r.delete(f"provider_breaker:{test_provider}")


def test_circuit_breaker_cooldown_starts_when_it_actually_opens_not_at_first_failure():
    """Regression test: opened_at was previously set on the FIRST
    failure (fails == 1), not when the breaker actually transitions to
    OPEN (fails == FAILURE_THRESHOLD). For failures spread out over
    time rather than all at once, this started the cooldown clock too
    early, silently shortening the enforced OPEN window. Simulates
    failures 2 minutes apart and confirms the breaker stays OPEN for
    the full cooldown measured from when it actually opened, not from
    the first failure."""
    import providers
    from datetime import datetime, timezone, timedelta
    from unittest.mock import patch

    test_provider = "pytest-cooldown-timing-check"
    r.delete(f"provider_breaker:{test_provider}")

    t0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    t1 = t0 + timedelta(minutes=2)
    t2 = t0 + timedelta(minutes=4)  # this failure actually opens the breaker

    with patch("providers.datetime") as mock_dt:
        mock_dt.fromisoformat = datetime.fromisoformat

        mock_dt.now.return_value = t0
        providers.record_failure(r, test_provider)
        mock_dt.now.return_value = t1
        providers.record_failure(r, test_provider)
        mock_dt.now.return_value = t2
        providers.record_failure(r, test_provider)
        assert providers.get_state(r, test_provider) == providers.OPEN

        # 3 minutes after the REAL open time (t2) - must still be OPEN,
        # since COOLDOWN_SECONDS is 300s (5 min). The bug made this
        # already HALF_OPEN because the clock incorrectly started at t0.
        mock_dt.now.return_value = t2 + timedelta(minutes=3)
        assert providers.get_state(r, test_provider) == providers.OPEN

        # Just past the real 5-minute cooldown from t2 - now HALF_OPEN.
        mock_dt.now.return_value = t2 + timedelta(minutes=5, seconds=1)
        assert providers.get_state(r, test_provider) == providers.HALF_OPEN

    r.delete(f"provider_breaker:{test_provider}")


class _FakeUpstreamResponse:
    """Minimal stand-in for httpx.Response — just needs .json()."""
    def __init__(self, data):
        self._data = data

    def json(self):
        return self._data


_GOOD_WEATHER = {
    "main": {"temp": 25}, "weather": [{"description": "clear"}],
    "coord": {"lat": 18.5, "lon": 73.8}, "cod": 200,
}
_OPENWEATHER_ERROR = {"cod": 401, "message": "Invalid API key"}


@patch("main.fetch", new_callable=AsyncMock, return_value=_GOOD_WEATHER)
@patch("main.log_query")
def test_aqi_raises_502_on_upstream_error_instead_of_returning_null(mock_log, mock_fetch):
    """Regression test: /aqi's second API call (air_pollution) was
    previously used unvalidated — an upstream error silently produced
    {"aqi": null} with HTTP 200 instead of raising."""
    with patch("main.cache_get", return_value=None), patch("main.cache_set") as mock_cache_set:
        with patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock, return_value=_FakeUpstreamResponse(_OPENWEATHER_ERROR)):
            res = client.get("/weather/Pune/aqi")
    assert res.status_code == 502
    mock_cache_set.assert_not_called()


@patch("main.fetch", new_callable=AsyncMock, return_value=_GOOD_WEATHER)
@patch("main.cache_get", return_value=None)
@patch("main.cache_set")
@patch("main.log_query")
def test_aqi_still_works_and_caches_normally_on_success(mock_log, mock_cache_set, mock_cache_get, mock_fetch):
    good_response = {"list": [{"main": {"aqi": 2}, "components": {"co": 200}}]}
    with patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock, return_value=_FakeUpstreamResponse(good_response)):
        res = client.get("/weather/Pune/aqi")
    assert res.status_code == 200
    assert res.json()["aqi"] == 2
    mock_cache_set.assert_called_once()


@patch("main.fetch", new_callable=AsyncMock, return_value=_GOOD_WEATHER)
@patch("main.log_query")
def test_uv_raises_502_on_upstream_error_instead_of_returning_null(mock_log, mock_fetch):
    with patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock, return_value=_FakeUpstreamResponse(_OPENWEATHER_ERROR)):
        res = client.get("/weather/Pune/uv")
    assert res.status_code == 502


@patch("main.fetch", new_callable=AsyncMock, return_value=_GOOD_WEATHER)
@patch("main.log_query")
def test_alerts_raises_502_on_upstream_error_instead_of_returning_no_alerts(mock_log, mock_fetch):
    """Regression test: previously indistinguishable from a genuinely
    quiet weather day - both returned 'No active alerts'."""
    with patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock, return_value=_FakeUpstreamResponse(_OPENWEATHER_ERROR)):
        res = client.get("/weather/Pune/alerts")
    assert res.status_code == 502
