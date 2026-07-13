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
