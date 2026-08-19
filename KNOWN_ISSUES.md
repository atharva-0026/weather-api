# Known Issues

## daily_log.py hit the wrong URL shape, logging 404 every day since launch

**Status:** Resolved (2026-08).

`daily_log.py` called `GET /weather?city=Pune` (query param), but the
actual route in `main.py` is path-based: `GET /weather/{city}`. Every
day from 2026-07-18 through 2026-08-16, the daily GitHub Actions cron
successfully ran, got a 404, and committed `{"error": 404}` to
`logs/` — with no failure signal anywhere. The workflow always showed
green.

**Fix:**
1. Changed the request to `GET /weather/Pune` (correct path form).
2. `daily_log.py` now exits non-zero when the fetch fails, so a broken
   fetch shows up as a **failed** GitHub Actions run instead of a
   silently-committed bad log entry. See `.github/workflows/daily-log.yml`
   — the commit step only runs after a successful logger step.
3. Added `test_daily_log_uses_correct_weather_url_shape` in
   `test_source_hygiene.py` to guard against this regressing.

Past log entries in `logs/` from before the fix were left as-is rather
than rewritten, since they're an accurate record of what actually
happened (a broken automation), not something to quietly erase.
