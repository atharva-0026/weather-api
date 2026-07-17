import requests
import datetime
import json
import os

API_BASE = "https://weather-api-production-fc6a.up.railway.app"
LOG_DIR = "logs"

def fetch_stats():
    try:
        r = requests.get(f"{API_BASE}/weather", params={"city": "Pune"}, timeout=10)
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

if __name__ == "__main__":
    main()
