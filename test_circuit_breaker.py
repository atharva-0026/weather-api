"""
Tests for the provider circuit breaker state machine in providers.py.

Covers the three states and their transitions:
  closed -> open        (after FAILURE_THRESHOLD consecutive failures)
  open -> half_open     (after COOLDOWN_SECONDS has elapsed)
  half_open -> closed   (trial request succeeds)
  half_open -> open     (trial request fails, cooldown resets)

Uses fakeredis so it runs without a real Redis instance.
"""

import fakeredis
import time
from datetime import datetime, timedelta

import providers


def make_redis():
    return fakeredis.FakeStrictRedis(decode_responses=True)


def test_starts_closed():
    r = make_redis()
    assert providers.get_state(r, "openweather") == providers.CLOSED
    assert providers.is_open(r, "openweather") is False


def test_opens_after_threshold_failures():
    r = make_redis()
    for _ in range(providers.FAILURE_THRESHOLD):
        providers.record_failure(r, "openweather")
    assert providers.get_state(r, "openweather") == providers.OPEN
    assert providers.is_open(r, "openweather") is True


def test_stays_closed_below_threshold():
    r = make_redis()
    for _ in range(providers.FAILURE_THRESHOLD - 1):
        providers.record_failure(r, "openweather")
    assert providers.get_state(r, "openweather") == providers.CLOSED


def test_transitions_to_half_open_after_cooldown():
    r = make_redis()
    for _ in range(providers.FAILURE_THRESHOLD):
        providers.record_failure(r, "openweather")

    # manually backdate opened_at to simulate cooldown having elapsed
    key = providers._breaker_key("openweather")
    past = (datetime.utcnow() - timedelta(seconds=providers.COOLDOWN_SECONDS + 1)).isoformat()
    r.hset(key, "opened_at", past)

    assert providers.get_state(r, "openweather") == providers.HALF_OPEN


def test_half_open_success_resets_breaker():
    r = make_redis()
    for _ in range(providers.FAILURE_THRESHOLD):
        providers.record_failure(r, "openweather")
    key = providers._breaker_key("openweather")
    past = (datetime.utcnow() - timedelta(seconds=providers.COOLDOWN_SECONDS + 1)).isoformat()
    r.hset(key, "opened_at", past)

    assert providers.get_state(r, "openweather") == providers.HALF_OPEN
    providers.record_success(r, "openweather")
    assert providers.get_state(r, "openweather") == providers.CLOSED


def test_half_open_failure_reopens_with_fresh_cooldown():
    r = make_redis()
    for _ in range(providers.FAILURE_THRESHOLD):
        providers.record_failure(r, "openweather")
    key = providers._breaker_key("openweather")
    past = (datetime.utcnow() - timedelta(seconds=providers.COOLDOWN_SECONDS + 1)).isoformat()
    r.hset(key, "opened_at", past)

    assert providers.get_state(r, "openweather") == providers.HALF_OPEN
    providers.record_failure(r, "openweather")
    # should be back to OPEN, not half_open, since the trial failed
    assert providers.get_state(r, "openweather") == providers.OPEN


def test_claim_trial_prevents_concurrent_half_open_requests():
    r = make_redis()
    for _ in range(providers.FAILURE_THRESHOLD):
        providers.record_failure(r, "openweather")
    key = providers._breaker_key("openweather")
    past = (datetime.utcnow() - timedelta(seconds=providers.COOLDOWN_SECONDS + 1)).isoformat()
    r.hset(key, "opened_at", past)

    assert providers.get_state(r, "openweather") == providers.HALF_OPEN
    providers.claim_trial(r, "openweather")
    # a second concurrent request should see OPEN, not get a second trial
    assert providers.get_state(r, "openweather") == providers.OPEN
