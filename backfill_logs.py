"""
One-off backfill for the logs/ entries broken by the daily_log.py URL
bug (see KNOWN_ISSUES.md and issue #1): every entry from 2026-07-18
through 2026-08-19 recorded {"error": 404} instead of real weather.

Those entries were deliberately left as an honest record of what
happened rather than silently erased. This script answers the open
question in #1 by re-fetching real historical weather for Pune from
Open-Meteo's archive API (free, no key, supports historical dates) and
replacing only the entries that are still broken - anything that
already holds real data (inside or outside the backfill range) is left
untouched, so it's safe to re-run.

Run once, manually: `python backfill_logs.py`
"""
import json
import os
import sys

import requests

LOG_DIR = "logs"
BACKFILL_START = "2026-07-18"
BACKFILL_END = "2026-08-19"
CITY = "Pune"
GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"


def geocode(city: str) -> tuple:
    res = requests.get(GEOCODE_URL, params={"name": city, "count": 1}, timeout=30)
    res.raise_for_status()
    results = res.json().get("results")
    if not results:
        raise RuntimeError(f"city not found: {city}")
    return results[0]["latitude"], results[0]["longitude"], results[0]["name"]


def broken_dates_in_range() -> list:
    """Dates (as "YYYY-MM-DD" strings) in [BACKFILL_START, BACKFILL_END]
    whose log file still records an error, sourced from the actual
    files on disk rather than hardcoding the list, so this stays
    correct even if some dates in the range were already fixed."""
    dates = []
    for fname in sorted(os.listdir(LOG_DIR)):
        if not fname.endswith(".json"):
            continue
        date = fname[: -len(".json")]
        if not (BACKFILL_START <= date <= BACKFILL_END):
            continue
        with open(os.path.join(LOG_DIR, fname)) as f:
            data = json.load(f)
        if "error" in data.get("pune_weather", {}):
            dates.append(date)
    return dates


def fetch_historical_stats(lat: float, lon: float, date: str) -> dict:
    """Mean temperature/humidity for `date`, averaged from Open-Meteo's
    hourly archive (the archive API doesn't offer a daily humidity
    aggregate, so this averages the hourly series itself)."""
    res = requests.get(ARCHIVE_URL, params={
        "latitude": lat, "longitude": lon,
        "start_date": date, "end_date": date,
        "hourly": "temperature_2m,relative_humidity_2m",
        "timezone": "auto",
    }, timeout=30)
    res.raise_for_status()
    hourly = res.json().get("hourly", {})
    temps = [v for v in hourly.get("temperature_2m", []) if v is not None]
    humids = [v for v in hourly.get("relative_humidity_2m", []) if v is not None]
    if not temps or not humids:
        raise RuntimeError(f"no historical data returned for {date}")
    return {
        "temp": round(sum(temps) / len(temps), 2),
        "humidity": round(sum(humids) / len(humids), 2),
    }


def main():
    dates = broken_dates_in_range()
    if not dates:
        print("No broken log entries found in range - nothing to backfill.")
        return

    lat, lon, name = geocode(CITY)
    print(f"Geocoded {CITY} -> ({lat}, {lon})")

    backfilled, failed = [], []
    for date in dates:
        try:
            stats = fetch_historical_stats(lat, lon, date)
        except Exception as e:
            print(f"SKIP {date}: {e}", file=sys.stderr)
            failed.append(date)
            continue

        path = os.path.join(LOG_DIR, f"{date}.json")
        data = {
            "date": date,
            "pune_weather": {
                "city": name,
                "temp": stats["temp"],
                "humidity": stats["humidity"],
                "description": "—",
                "lat": lat,
                "lon": lon,
                "provider": "open-meteo-archive",
                # Marks this as re-fetched after the fact, not a live
                # same-day reading, so the record stays honest about
                # its provenance (matches the "don't quietly erase
                # what happened" principle in KNOWN_ISSUES.md).
                "backfilled": True,
            },
        }
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
        print(f"Backfilled {date}: temp={stats['temp']} humidity={stats['humidity']}")
        backfilled.append(date)

    print(f"\nDone: {len(backfilled)} backfilled, {len(failed)} failed out of {len(dates)}.")
    if failed:
        print("Failed dates:", ", ".join(failed))
        sys.exit(1)


if __name__ == "__main__":
    main()
