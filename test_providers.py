"""
Tests for providers.fetch_openmeteo, in particular the regression that
motivated this file: Open-Meteo can return HTTP 200 with a valid-JSON
body that has no "current" key (e.g. rate-limiting a shared outbound
IP, which is common on platforms like Render). The old code silently
returned {"temp": None, "humidity": None, ...} and called it a success,
skipping the circuit breaker / failover error tracking entirely.

Uses asyncio.run() directly (matching the rest of the test suite,
which has no pytest-asyncio dependency) rather than async test
functions.
"""
import asyncio

import httpx
import pytest
from unittest.mock import AsyncMock, patch

from providers import fetch_openmeteo


def _mock_response(json_body, status_code=200):
    return httpx.Response(
        status_code=status_code,
        json=json_body,
        request=httpx.Request("GET", "https://example.com"),
    )


def test_fetch_openmeteo_returns_real_data_on_success():
    geo_response = _mock_response({"results": [{"latitude": 18.52, "longitude": 73.86, "name": "Pune"}]})
    forecast_response = _mock_response({
        "current": {"temperature_2m": 23.2, "relative_humidity_2m": 85}
    })

    with patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = [geo_response, forecast_response]
        result = asyncio.run(fetch_openmeteo("Pune", "metric"))

    assert result["temp"] == 23.2
    assert result["humidity"] == 85
    assert result["provider"] == "open-meteo"


def test_fetch_openmeteo_raises_instead_of_returning_nulls():
    """Regression test for the exact bug found in production: a 200
    response with no "current" key must raise, not silently succeed
    with null temp/humidity."""
    geo_response = _mock_response({"results": [{"latitude": 18.52, "longitude": 73.86, "name": "Pune"}]})
    # Simulates Open-Meteo's rate-limit / error response shape: valid
    # JSON, 200 status, but no "current" key at all.
    bad_forecast_response = _mock_response({"error": True, "reason": "rate limited"})

    with patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = [geo_response, bad_forecast_response]
        with pytest.raises(RuntimeError, match="no current weather data"):
            asyncio.run(fetch_openmeteo("Pune", "metric"))


def test_fetch_openmeteo_raises_on_partial_null_data():
    """Even if only one of temp/humidity is missing, must still raise —
    a half-populated reading is just as unusable as a fully null one."""
    geo_response = _mock_response({"results": [{"latitude": 18.52, "longitude": 73.86, "name": "Pune"}]})
    partial_response = _mock_response({"current": {"temperature_2m": 23.2}})

    with patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = [geo_response, partial_response]
        with pytest.raises(RuntimeError, match="no current weather data"):
            asyncio.run(fetch_openmeteo("Pune", "metric"))


def test_fetch_openmeteo_raises_on_unknown_city():
    empty_geo_response = _mock_response({"results": []})

    with patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = [empty_geo_response]
        with pytest.raises(RuntimeError, match="city not found"):
            asyncio.run(fetch_openmeteo("Nonexistentville", "metric"))
