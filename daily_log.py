import requests
import datetime
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

def fetch_stats():
    try:
        # /weather/{city} requires OPENWEATHER_API_KEY to be configured
        # on the deployment - /failover works with zero keys configured
        # (falls back through WeatherAPI, then Open-Meteo), so this
        # daily job doesn't depend on that key being set correctly to
        # succeed. See KNOWN_ISSUES.md for the history of failures here.
        r = requests.get(f"{API_BASE}/weather/Pune/failover", timeout=10)
        weather = r.json() if r.status_code == 200 else {"error": r.status_code}
    except Exception as e:
        weather = {"error": str(e)}

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
