"""
API key issuance and daily quota tracking, backed by Redis.

Keys are opaque tokens stored as a Redis hash `apikey:{key}` with a tier
and creation date. Usage is tracked per key per day at `usage:{key}:{date}`
with a 24h TTL, so quotas reset automatically at midnight UTC.
"""

import secrets
from datetime import datetime, timezone

from fastapi import HTTPException

TIERS = {
    "free": 200,
    "pro": 2000,
}


def generate_api_key() -> str:
    return "wapi_" + secrets.token_urlsafe(24)


def create_key(r, tier: str = "free") -> dict:
    if tier not in TIERS:
        tier = "free"
    key = generate_api_key()
    r.hset(f"apikey:{key}", mapping={"tier": tier, "created": datetime.now(timezone.utc).isoformat()})
    return {"api_key": key, "tier": tier, "daily_limit": TIERS[tier]}


def _usage_key(api_key: str) -> str:
    # Must use UTC, not date.today() (local system date) — the module
    # docstring promises quotas "reset automatically at midnight UTC".
    # date.today() would silently reset at local midnight instead if
    # this ever runs somewhere with a non-UTC system timezone.
    today_utc = datetime.now(timezone.utc).date()
    return f"usage:{api_key}:{today_utc.isoformat()}"


def validate_and_track(r, api_key: str) -> dict:
    meta = r.hgetall(f"apikey:{api_key}")
    if not meta:
        raise HTTPException(status_code=401, detail="Invalid API key")
    tier = meta.get("tier", "free")
    limit = TIERS.get(tier, TIERS["free"])
    usage_key = _usage_key(api_key)
    count = r.incr(usage_key)
    if count == 1:
        r.expire(usage_key, 86400)
    if count > limit:
        raise HTTPException(status_code=429, detail=f"Daily quota exceeded ({limit} requests/day on {tier} tier)")
    return {"tier": tier, "used": count, "limit": limit}


def get_usage(r, api_key: str) -> dict:
    meta = r.hgetall(f"apikey:{api_key}")
    if not meta:
        raise HTTPException(status_code=401, detail="Invalid API key")
    tier = meta.get("tier", "free")
    limit = TIERS.get(tier, TIERS["free"])
    count = int(r.get(_usage_key(api_key)) or 0)
    return {"tier": tier, "used": count, "limit": limit, "remaining": max(0, limit - count)}


MAX_FAVORITES = 25


def _require_valid_key(r, api_key: str) -> None:
    if not r.hgetall(f"apikey:{api_key}"):
        raise HTTPException(status_code=401, detail="Invalid API key")


def _favorites_key(api_key: str) -> str:
    return f"favorites:{api_key}"


def get_favorites(r, api_key: str) -> dict:
    _require_valid_key(r, api_key)
    # Stored as a hash of {lowercased city: original casing} so
    # "Mumbai" and "mumbai" count as the same favorite (same reasoning
    # as /compare's case-insensitive duplicate check) while still
    # displaying whatever casing was actually added.
    return {"favorites": sorted(r.hgetall(_favorites_key(api_key)).values())}


def add_favorite(r, api_key: str, city: str) -> dict:
    _require_valid_key(r, api_key)
    city = city.strip()
    if not city:
        raise HTTPException(status_code=400, detail="city must not be empty")
    key = _favorites_key(api_key)
    field = city.lower()
    if r.hlen(key) >= MAX_FAVORITES and not r.hexists(key, field):
        raise HTTPException(status_code=400, detail=f"Maximum of {MAX_FAVORITES} favorites reached")
    r.hset(key, field, city)
    return get_favorites(r, api_key)


def remove_favorite(r, api_key: str, city: str) -> dict:
    _require_valid_key(r, api_key)
    r.hdel(_favorites_key(api_key), city.strip().lower())
    return get_favorites(r, api_key)
