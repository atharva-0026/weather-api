"""
Tests for backfill_logs.py - the one-off script that re-fetches real
historical weather for the logs/ entries broken by the daily_log.py
URL bug (see KNOWN_ISSUES.md and issue #1).
"""
import json
import os
from unittest.mock import MagicMock, patch

import pytest

import backfill_logs


def _write_log(tmp_path, date, pune_weather):
    (tmp_path / f"{date}.json").write_text(
        json.dumps({"date": date, "pune_weather": pune_weather})
    )


def _mock_response(json_body, status_code=200):
    res = MagicMock()
    res.status_code = status_code
    res.json.return_value = json_body
    res.raise_for_status.side_effect = (
        None if status_code == 200 else Exception(f"HTTP {status_code}")
    )
    return res


@pytest.fixture(autouse=True)
def _use_tmp_log_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(backfill_logs, "LOG_DIR", str(tmp_path))
    return tmp_path


def test_broken_dates_in_range_only_includes_error_entries_in_window(tmp_path):
    _write_log(tmp_path, "2026-07-18", {"error": 404})  # in range, broken
    _write_log(tmp_path, "2026-08-19", {"error": 404})  # in range, broken (boundary)
    _write_log(tmp_path, "2026-08-01", {"city": "Pune", "temp": 25})  # in range, already fine
    _write_log(tmp_path, "2026-08-20", {"error": 404})  # outside range
    _write_log(tmp_path, "2026-07-17", {"error": 404})  # outside range (boundary)

    assert backfill_logs.broken_dates_in_range() == ["2026-07-18", "2026-08-19"]


def test_broken_dates_in_range_empty_when_nothing_broken(tmp_path):
    _write_log(tmp_path, "2026-07-20", {"city": "Pune", "temp": 25})
    assert backfill_logs.broken_dates_in_range() == []


def test_fetch_historical_stats_averages_hourly_series():
    response = _mock_response({
        "hourly": {
            "temperature_2m": [20.0, 22.0, 24.0],
            "relative_humidity_2m": [50, 60, 70],
        }
    })
    with patch.object(backfill_logs.httpx, "get", return_value=response):
        stats = backfill_logs.fetch_historical_stats(18.52, 73.86, "2026-07-18")

    assert stats == {"temp": 22.0, "humidity": 60.0}


def test_fetch_historical_stats_skips_null_readings_in_average():
    response = _mock_response({
        "hourly": {
            "temperature_2m": [20.0, None, 24.0],
            "relative_humidity_2m": [50, None, 70],
        }
    })
    with patch.object(backfill_logs.httpx, "get", return_value=response):
        stats = backfill_logs.fetch_historical_stats(18.52, 73.86, "2026-07-18")

    assert stats == {"temp": 22.0, "humidity": 60.0}


def test_fetch_historical_stats_raises_when_no_data_returned():
    response = _mock_response({"hourly": {"temperature_2m": [], "relative_humidity_2m": []}})
    with patch.object(backfill_logs.httpx, "get", return_value=response):
        with pytest.raises(RuntimeError, match="no historical data"):
            backfill_logs.fetch_historical_stats(18.52, 73.86, "2026-07-18")


def test_main_rewrites_only_broken_entries_and_leaves_others_untouched(tmp_path):
    _write_log(tmp_path, "2026-07-18", {"error": 404})
    _write_log(tmp_path, "2026-08-01", {"city": "Pune", "temp": 99, "untouched": True})

    geocode_response = _mock_response(
        {"results": [{"latitude": 18.52, "longitude": 73.86, "name": "Pune"}]}
    )
    archive_response = _mock_response({
        "hourly": {
            "temperature_2m": [28.0, 30.0],
            "relative_humidity_2m": [55, 65],
        }
    })

    with patch.object(backfill_logs.httpx, "get", side_effect=[geocode_response, archive_response]):
        backfill_logs.main()

    backfilled = json.loads((tmp_path / "2026-07-18.json").read_text())
    assert backfilled["pune_weather"]["temp"] == 29.0
    assert backfilled["pune_weather"]["humidity"] == 60.0
    assert backfilled["pune_weather"]["provider"] == "open-meteo-archive"
    assert backfilled["pune_weather"]["backfilled"] is True
    assert "error" not in backfilled["pune_weather"]

    untouched = json.loads((tmp_path / "2026-08-01.json").read_text())
    assert untouched["pune_weather"] == {"city": "Pune", "temp": 99, "untouched": True}


def test_main_exits_nonzero_when_any_date_fails(tmp_path):
    _write_log(tmp_path, "2026-07-18", {"error": 404})

    geocode_response = _mock_response(
        {"results": [{"latitude": 18.52, "longitude": 73.86, "name": "Pune"}]}
    )
    failing_archive_response = _mock_response({"hourly": {"temperature_2m": [], "relative_humidity_2m": []}})

    with patch.object(backfill_logs.httpx, "get", side_effect=[geocode_response, failing_archive_response]):
        with pytest.raises(SystemExit) as exc_info:
            backfill_logs.main()

    assert exc_info.value.code == 1
    # The broken entry must be left as-is, not overwritten with partial/garbage data.
    still_broken = json.loads((tmp_path / "2026-07-18.json").read_text())
    assert still_broken["pune_weather"] == {"error": 404}


def test_main_is_noop_when_nothing_broken(tmp_path):
    _write_log(tmp_path, "2026-07-20", {"city": "Pune", "temp": 25})

    with patch.object(backfill_logs.httpx, "get") as mock_get:
        backfill_logs.main()

    mock_get.assert_not_called()
