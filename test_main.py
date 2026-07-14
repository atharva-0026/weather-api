import os
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def test_version():
    res = client.get("/version")
    assert res.status_code == 200
    body = res.json()
    assert body["service"] == "weather-api"
    assert body["version"] == "3.0.0"


def test_health():
    res = client.get("/health")
    assert res.status_code == 200
    assert "status" in res.json()


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


def test_history_not_found():
    res = client.get("/history/NonexistentCityXYZ")
    assert res.status_code in (404, 429)


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
