"""
Unit tests for ml_forecast.py's model cache, in particular the
regression that motivated _cache_key(): the cache used to key on city
string alone, ignoring the actual coordinates the model was trained on.
"""
import ml_forecast


def test_cache_key_differs_for_different_coordinates_same_city_name():
    """Regression test: the cache previously used the city string alone
    as its key, so if the same name ever geocoded to different
    coordinates (ambiguous city names like 'Springfield'), a model
    trained for the wrong location would be silently served with zero
    validation."""
    key_illinois = ml_forecast._cache_key("Springfield", 39.78, -89.65)
    key_massachusetts = ml_forecast._cache_key("Springfield", 42.10, -72.59)
    assert key_illinois != key_massachusetts


def test_cache_key_same_for_cosmetic_differences_at_same_location():
    """Case, whitespace, and tiny float noise (same place, slightly
    different geocoded precision) should still share one cache entry —
    no need to retrain for a purely cosmetic difference."""
    key1 = ml_forecast._cache_key("Pune", 18.52, 73.86)
    key2 = ml_forecast._cache_key(" pune ", 18.5201, 73.8599)
    assert key1 == key2


def test_build_features_shape():
    from datetime import date
    dates = [date(2026, 1, 1), date(2026, 1, 2), date(2026, 1, 3)]
    features = ml_forecast._build_features(dates)
    assert features.shape == (3, 3)  # sin, cos, trend columns


def test_build_features_trend_defaults_to_starting_at_zero():
    from datetime import date
    dates = [date(2026, 1, 1), date(2026, 1, 2), date(2026, 1, 3)]
    features = ml_forecast._build_features(dates)
    assert list(features[:, 2]) == [0.0, 1.0, 2.0]


def test_build_features_trend_offset_continues_the_sequence():
    """Regression test: predict_next_days() previously called
    _build_features(future_dates) with no offset, so the trend feature
    reset to 0 for the first future prediction day instead of
    continuing from where training left off (e.g. 365 after a full
    year of training data) - an out-of-distribution value for a
    feature meant to capture drift across the training period."""
    from datetime import date
    dates = [date(2026, 1, 1), date(2026, 1, 2), date(2026, 1, 3)]
    features = ml_forecast._build_features(dates, trend_offset=365)
    assert list(features[:, 2]) == [365.0, 366.0, 367.0]


def test_predict_next_days_continues_trend_from_training_length():
    from datetime import date
    from unittest.mock import MagicMock

    fake_model = MagicMock()
    fake_model.predict.return_value = [20.0, 21.0]

    predict_next_days = ml_forecast.predict_next_days
    predict_next_days(fake_model, date(2026, 1, 31), train_length=31, n=2)

    # Whatever feature matrix was actually passed to model.predict()
    # must have trend values continuing from 31, not resetting to 0.
    called_features = fake_model.predict.call_args[0][0]
    assert list(called_features[:, 2]) == [31.0, 32.0]


def test_train_model_raises_on_insufficient_data():
    daily = {
        "time": ["2026-01-01", "2026-01-02"],
        "temperature_2m_max": [20.0, 21.0],
    }
    try:
        ml_forecast.train_model(daily)
        assert False, "expected ValueError for insufficient data"
    except ValueError as e:
        assert "Not enough historical data" in str(e)


def test_train_model_filters_nan_values():
    import numpy as np

    dates = [f"2026-01-{d:02d}" for d in range(1, 32)]
    temps = [20.0 + (i % 5) for i in range(31)]
    temps[5] = float("nan")  # one bad reading should be filtered, not crash
    daily = {"time": dates, "temperature_2m_max": temps}

    model, last_date, train_length = ml_forecast.train_model(daily)
    assert model is not None
    assert last_date.isoformat() == "2026-01-31"
    assert train_length == 30  # 31 days minus the 1 filtered NaN
