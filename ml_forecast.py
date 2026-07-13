"""
ML-based temperature forecasting.

Trains a RandomForestRegressor per city on 1 year of historical daily
max temperatures (free Open-Meteo archive API, no key required), using
cyclical day-of-year features plus a linear trend term. Retrains once
per day per city, cached in-process.
"""

import httpx
import numpy as np
from datetime import date, timedelta

from sklearn.ensemble import RandomForestRegressor

HISTORICAL_URL = "https://archive-api.open-meteo.com/v1/archive"

# city -> {"model": RandomForestRegressor, "trained_on": date, "last_date": date}
_model_cache = {}


async def fetch_historical(lat: float, lon: float, days: int = 365) -> dict:
    end = date.today() - timedelta(days=1)
    start = end - timedelta(days=days)
    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "daily": "temperature_2m_max,temperature_2m_min",
        "timezone": "auto",
    }
    async with httpx.AsyncClient(timeout=20) as client:
        res = await client.get(HISTORICAL_URL, params=params)
        res.raise_for_status()
        return res.json()


def _build_features(dates: list) -> np.ndarray:
    doy = np.array([d.timetuple().tm_yday for d in dates])
    sin = np.sin(2 * np.pi * doy / 365.25)
    cos = np.cos(2 * np.pi * doy / 365.25)
    trend = np.arange(len(dates))
    return np.column_stack([sin, cos, trend])


def train_model(daily: dict):
    dates = [date.fromisoformat(d) for d in daily["time"]]
    y = np.array(daily["temperature_2m_max"], dtype=float)
    mask = ~np.isnan(y)
    dates_clean = [d for d, m in zip(dates, mask) if m]
    X = _build_features(dates_clean)
    y = y[mask]
    if len(y) < 30:
        raise ValueError("Not enough historical data to train a model")
    model = RandomForestRegressor(n_estimators=200, max_depth=6, random_state=42)
    model.fit(X, y)
    return model, dates_clean[-1]


async def get_or_train_model(city: str, lat: float, lon: float):
    cached = _model_cache.get(city)
    if cached and cached["trained_on"] == date.today():
        return cached["model"], cached["last_date"]
    data = await fetch_historical(lat, lon)
    model, last_date = train_model(data["daily"])
    _model_cache[city] = {"model": model, "trained_on": date.today(), "last_date": last_date}
    return model, last_date


def predict_next_days(model, last_date: date, n: int = 5) -> list:
    future_dates = [last_date + timedelta(days=i + 1) for i in range(n)]
    X = _build_features(future_dates)
    preds = model.predict(X)
    return [
        {"date": d.isoformat(), "predicted_temp_max": round(float(p), 1)}
        for d, p in zip(future_dates, preds)
    ]
