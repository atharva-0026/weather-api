"""
Unit tests for auth.py's API key issuance and quota tracking.

Uses fakeredis, matching test_circuit_breaker.py's pattern, so this
runs without a real Redis instance.
"""
from unittest.mock import patch
from datetime import datetime, timezone

import fakeredis
import pytest
from fastapi import HTTPException

import auth


def make_redis():
    return fakeredis.FakeStrictRedis(decode_responses=True)


def test_generate_api_key_has_expected_prefix():
    key = auth.generate_api_key()
    assert key.startswith("wapi_")
    assert len(key) > len("wapi_") + 20


def test_create_key_defaults_to_free_tier_for_unknown_tier():
    r = make_redis()
    result = auth.create_key(r, tier="not-a-real-tier")
    assert result["tier"] == "free"
    assert result["daily_limit"] == auth.TIERS["free"]


def test_validate_and_track_rejects_unknown_key():
    r = make_redis()
    with pytest.raises(HTTPException) as exc_info:
        auth.validate_and_track(r, "wapi_does_not_exist")
    assert exc_info.value.status_code == 401


def test_validate_and_track_enforces_daily_quota():
    r = make_redis()
    key = auth.create_key(r, tier="free")["api_key"]

    for _ in range(auth.TIERS["free"]):
        auth.validate_and_track(r, key)

    with pytest.raises(HTTPException) as exc_info:
        auth.validate_and_track(r, key)
    assert exc_info.value.status_code == 429


def test_usage_key_uses_utc_date_not_local_system_date():
    """Regression test: _usage_key() previously used date.today(),
    which returns the LOCAL system date, not UTC - contradicting the
    module docstring's explicit promise that quotas "reset
    automatically at midnight UTC". Mock datetime.now(timezone.utc)
    directly and confirm the usage key reflects that UTC date."""
    fixed_utc = datetime(2026, 1, 2, 0, 15, tzinfo=timezone.utc)  # just past UTC midnight

    with patch("auth.datetime") as mock_dt:
        mock_dt.now.return_value = fixed_utc
        key = auth._usage_key("wapi_testkey")

    assert key == "usage:wapi_testkey:2026-01-02"


def test_get_usage_for_unknown_key_raises_401():
    r = make_redis()
    with pytest.raises(HTTPException) as exc_info:
        auth.get_usage(r, "wapi_does_not_exist")
    assert exc_info.value.status_code == 401


def test_get_usage_reports_remaining_quota():
    r = make_redis()
    key = auth.create_key(r, tier="free")["api_key"]
    auth.validate_and_track(r, key)
    auth.validate_and_track(r, key)

    usage = auth.get_usage(r, key)
    assert usage["used"] == 2
    assert usage["remaining"] == auth.TIERS["free"] - 2
