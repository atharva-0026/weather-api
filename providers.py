"""
Multi-provider weather fetching with automatic failover.

Tries OpenWeather first, then WeatherAPI.com (if configured), then
Open-Meteo (free, no key) as a last resort. Each provider has a Redis-backed
circuit breaker with three states:

  CLOSED    - normal operation, requests go through
  OPEN      - provider failed >= FAILURE_THRESHOLD times, skipped entirely
  HALF_OPEN - cooldown has passed, exactly one trial request is allowed
              through to test if the provider has recovered

This avoids two failure modes of a plain open/closed breaker: hammering a
dead provider forever, and flipping straight back to fully-trusted after
cooldown even if it's still broken.
"""

import os
import httpx
from datetime import datetime, timedelta

OPENWEATHER_KEY = os.getenv("OPENWEATHER_API_KEY")
WEATHERAPI_KEY = os.getenv("WEATHERAPI_KEY")

OPENWEATHER_URL = "https://api.openweathermap.org/data/2.5/weather"
WEATHERAPI_URL = "https://api.weatherapi.com/v1/current.json"
OPENMETEO_GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
OPENMETEO_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

FAILURE_THRESHOLD = 3
COOLDOWN_SECONDS = 300

CLOSED = "closed"
OPEN = "open"
HALF_OPEN = "half_open"


def _breaker_key(name: str) -> str:
    return f"provider_breaker:{name}"


def get_state(r, name: str) -> str:
    """Returns CLOSED, OPEN, or HALF_OPEN for this provider, lazily
    transitioning OPEN -> HALF_OPEN once cooldown has elapsed."""
    data = r.hgetall(_breaker_key(name))
    if not data:
        return CLOSED

    fails = int(data.get("fails", 0))
    if fails < FAILURE_THRESHOLD:
        return CLOSED

    opened_at = data.get("opened_at")
    if not opened_at:
        return CLOSED

    elapsed = datetime.utcnow() - datetime.fromisoformat(opened_at)
    if elapsed < timedelta(seconds=COOLDOWN_SECONDS):
        return OPEN

    # cooldown elapsed - allow exactly one trial request through
    if data.get("trial_in_flight") == "1":
        # another request already claimed the trial slot; stay OPEN for us
        return OPEN
    return HALF_OPEN


def claim_trial(r, name: str):
    """Marks that this request is using the single half-open trial slot,
    so concurrent requests don't all pile onto the recovering provider."""
    r.hset(_breaker_key(name), "trial_in_flight", "1")
    r.expire(_breaker_key(name), COOLDOWN_SECONDS * 2)


def is_open(r, name: str) -> bool:
    """Back-compat helper: treat only the OPEN state as 'skip this provider'.
    HALF_OPEN is intentionally not 'open' - it's meant to let one request through."""
    return get_state(r, name) == OPEN


def record_success(r, name: str):
    """Any success - including a half-open trial - fully resets the breaker."""
    r.delete(_breaker_key(name))


def record_failure(r, name: str):
    key = _breaker_key(name)
    state_before = get_state(r, name)
    fails = r.hincrby(key, "fails", 1)
    if fails == 1:
        r.hset(key, "opened_at", datetime.utcnow().isoformat())
    if state_before == HALF_OPEN:
        # trial failed - reopen the breaker with a fresh cooldown window
        r.hset(key, "opened_at", datetime.utcnow().isoformat())
        r.hdel(key, "trial_in_flight")
    r.expire(key, COOLDOWN_SECONDS * 2)


async def fetch_openweather(city: str, units: str) -> dict:
    if not OPENWEATHER_KEY:
        raise RuntimeError("not configured")
    async with httpx.AsyncClient(timeout=10) as client:
        res = await client.get(OPENWEATHER_URL, params={"q": city, "units": units, "appid": OPENWEATHER_KEY})
        data = res.json()
        if data.get("cod") not in (200, "200"):
            raise RuntimeError(data.get("message", "error"))
        return {
            "city": data["name"],
            "temp": data["main"]["temp"],
            "humidity": data["main"]["humidity"],
            "description": data["weather"][0]["description"],
            "lat": data["coord"]["lat"],
            "lon": data["coord"]["lon"],
            "provider": "openweather",
        }


async def fetch_weatherapi(city: str, units: str) -> dict:
    if not WEATHERAPI_KEY:
        raise RuntimeError("not configured")
    async with httpx.AsyncClient(timeout=10) as client:
        res = await client.get(WEATHERAPI_URL, params={"key": WEATHERAPI_KEY, "q": city})
        data = res.json()
        if "error" in data:
            raise RuntimeError(data["error"].get("message", "error"))
        temp = data["current"]["temp_c"] if units == "metric" else data["current"]["temp_f"]
        return {
            "city": data["location"]["name"],
            "temp": temp,
            "humidity": data["current"]["humidity"],
            "description": data["current"]["condition"]["text"],
            "lat": data["location"]["lat"],
            "lon": data["location"]["lon"],
            "provider": "weatherapi",
        }


async def fetch_openmeteo(city: str, units: str) -> dict:
    async with httpx.AsyncClient(timeout=10) as client:
        geo = await client.get(OPENMETEO_GEOCODE_URL, params={"name": city, "count": 1})
        results = geo.json().get("results")
        if not results:
            raise RuntimeError("city not found")
        lat, lon, name = results[0]["latitude"], results[0]["longitude"], results[0]["name"]
        temp_unit = "fahrenheit" if units == "imperial" else "celsius"
        res = await client.get(OPENMETEO_FORECAST_URL, params={
            "latitude": lat, "longitude": lon,
            "current": "temperature_2m,relative_humidity_2m",
            "temperature_unit": temp_unit,
        })
        current = res.json().get("current", {})
        return {
            "city": name,
            "temp": current.get("temperature_2m"),
            "humidity": current.get("relative_humidity_2m"),
            "description": "—",
            "lat": lat,
            "lon": lon,
            "provider": "open-meteo",
        }


PROVIDERS = [
    ("openweather", fetch_openweather),
    ("weatherapi", fetch_weatherapi),
    ("open-meteo", fetch_openmeteo),
]


async def fetch_with_failover(r, city: str, units: str) -> dict:
    errors = {}
    for name, fn in PROVIDERS:
        state = get_state(r, name)

        if state == OPEN:
            errors[name] = "circuit open, cooling down"
            continue

        if state == HALF_OPEN:
            claim_trial(r, name)

        try:
            result = await fn(city, units)
            record_success(r, name)
            return result
        except Exception as e:
            record_failure(r, name)
            errors[name] = str(e)
    raise RuntimeError(f"all providers failed: {errors}")


def provider_status(r) -> list:
    status = []
    for name, _ in PROVIDERS:
        state = get_state(r, name)
        status.append({
            "provider": name,
            "state": state,
            "healthy": state == CLOSED,
            "recent_failures": int(r.hget(_breaker_key(name), "fails") or 0),
        })
    return status
