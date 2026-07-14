"""
API key issuance and daily quota tracking, backed by Redis.

Keys are opaque tokens stored as a Redis hash `apikey:{key}` with a tier
and creation date. Usage is tracked per key per day at `usage:{key}:{date}`
with a 24h TTL, so quotas reset automatically at midnight UTC.
"""

import secrets
from datetime import date, datetime

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
    r.hset(f"apikey:{key}", mapping={"tier": tier, "created": datetime.utcnow().isoformat()})
    return {"api_key": key, "tier": tier, "daily_limit": TIERS[tier]}


def _usage_key(api_key: str) -> str:
    return f"usage:{api_key}:{date.today().isoformat()}"


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
