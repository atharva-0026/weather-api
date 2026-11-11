# Known Issues

## Daily log fails intermittently with HTTP 503 on a sleeping Render instance

**Status:** Open (2026-10). Retries did not fix it; diagnosing.

From 2026-09 the daily-log job failed on most days with `fetch failed: 503`
roughly 30 seconds into the request (09-19, 09-23, 09-29, then every day
from 10-01), while succeeding on other days with the same code. That
pattern matches the free Render instance being asleep at 09:00 IST: the
first request wakes it and gets a 503 before the app is ready.

**Fix:** `daily_log.py` now retries 5xx responses and connection errors
(waits 20s, 40s, 60s) before failing, and keeps the first 300 characters of
the error body in the log so a Render wake-up page can be told apart from
`/failover`'s own "all providers failed" 503. 4xx is not retried. Covered by
`test_daily_log.py`.

**Update (10-13):** Runs on 10-11, 10-12 and 10-13 still got 503 on all four
attempts over three minutes, so this is not a cold start: the API is up and
`/failover` itself answers 503 ("all providers failed"). The log file holding
the error body is never committed on a failed run, so the cause was not
visible. The job now prints the body and `/providers/status` (each provider's
circuit breaker) to the Actions log on failure. Next failing run will name the
provider. Likely suspects: Open-Meteo rate-limiting Render's shared outbound IP
with no OpenWeather or WeatherAPI key configured on the deployment. Note that
three failures open every breaker for 5 minutes, so later retries in the same
run only see "circuit open".

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
