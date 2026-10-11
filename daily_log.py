import requests
import datetime
import time
import json
import os
import sys

# Migrated from Railway to Render (2026-08) after Railway's free trial
# expired and paused the deployment - see KNOWN_ISSUES.md. This was
# left pointing at the dead Railway URL after the migration, which is
# why every daily run failed with a connection error from
# 2026-08-20 onward (visible in the Actions history, not in logs/
# since the sys.exit(1) fix below correctly stopped committing bad data
# - it just never stopped failing, because it was failing for a NEW
# reason after that fix landed).
API_BASE = "https://weather-api-4nmo.onrender.com"
LOG_DIR = "logs"

# A once-a-day request almost always lands on a sleeping Render instance.
# Since 2026-09 those first requests have come back as HTTP 503 after
# ~30s (Actions history: 503 on 09-19, 09-23, 09-29, and daily from
# 10-01) while the same job succeeds on days the instance is already up.
# The first request wakes it, so retry 5xx/connection errors with a pause
# instead of failing the whole day on the wake-up call. 4xx is a real bug
# (wrong URL, route removed) and is not retried.
RETRY_DELAYS = (20, 40, 60)


def _fetch_once():
    r = requests.get(f"{API_BASE}/weather/Pune/failover", timeout=60)
    if r.status_code == 200:
        return r.json(), False
    # Keep the start of the error body in the log: "503" alone can't tell
    # a Render wake-up page from main.py's "all providers failed" detail.
    return {"error": r.status_code, "detail": r.text[:300]}, r.status_code >= 500


def fetch_stats(sleep=time.sleep, delays=RETRY_DELAYS):
    # /weather/{city} requires OPENWEATHER_API_KEY to be configured on
    # the deployment - /failover works with zero keys configured (falls
    # back through WeatherAPI, then Open-Meteo), so this daily job
    # doesn't depend on that key being set correctly to succeed. See
    # KNOWN_ISSUES.md for the history of failures here.
    #
    # timeout=60, not 10: Render's free tier can take 50+ seconds to
    # cold-start (confirmed via Render's own dashboard warning).
    attempts = len(delays) + 1
    for attempt in range(1, attempts + 1):
        try:
            weather, retryable = _fetch_once()
        except requests.RequestException as e:
            weather, retryable = {"error": str(e)}, True
        if "error" not in weather or not retryable or attempt == attempts:
            break
        wait = delays[attempt - 1]
        print(f"attempt {attempt}/{attempts} failed ({weather['error']}), retrying in {wait}s", file=sys.stderr)
        sleep(wait)

    return {
        "date": datetime.date.today().isoformat(),
        "pune_weather": weather,
    }

def main():
    os.makedirs(LOG_DIR, exist_ok=True)
    data = fetch_stats()
    today = data["date"]
    path = os.path.join(LOG_DIR, f"{today}.json")
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    print(f"Logged {today}")

    # Every day from 2026-07-18 to 2026-08-16 silently logged
    # {"error": 404} due to a URL bug (fixed above) with no failure
    # signal anywhere. Exit non-zero on error so a broken fetch shows
    # up as a failed GitHub Actions run instead of a silent bad commit.
    if "error" in data["pune_weather"]:
        print(f"WARNING: fetch failed: {data['pune_weather']['error']}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
