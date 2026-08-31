# Weather API

![Python](https://img.shields.io/badge/python-3.11-blue) ![FastAPI](https://img.shields.io/badge/FastAPI-005571) ![Redis](https://img.shields.io/badge/Redis-cache-red) ![Tests](https://github.com/atharva-0026/weather-api/actions/workflows/tests.yml/badge.svg)

**Live:** currently down — Railway's free trial expired and paused the deployment (see #1). Migrating to Render, see Deploy section below.

Production-grade REST API for real-time weather data with a dark dashboard UI.

## Features
- Current weather, 5-day forecast, UV index, air quality index, city comparison
- Multi-provider failover (OpenWeather → WeatherAPI → Open-Meteo) with Redis-backed circuit breaker
- ML-based temperature forecast (RandomForestRegressor trained on 1yr historical data per city)
- Redis caching (5 min TTL, auto-refresh every 30 mins)
- Rate limiting (10 req/min per IP)
- Query history + leaderboard
- Severe weather alerts
- Metric/imperial toggle
- Request logging
- Health check endpoint
- Dark dashboard UI at `/ui`
- Swagger docs at `/docs`

## Stack
`FastAPI` `Redis` `Docker` `Python` `HTML/CSS`

## Run
```bash
cp .env.example .env   # optional — fill in provider API keys if you have them
docker compose up --build
```

## Deploy (free tier: Render + Upstash)
1. **Redis:** Create a free database at [upstash.com](https://upstash.com) → copy its `rediss://...` connection string.
2. **Web service:** Push this repo to GitHub (already done), then in the [Render dashboard](https://dashboard.render.com) → New → Blueprint → connect this repo. Render reads `render.yaml` automatically.
3. When prompted, fill in the dashboard-only env vars:
   - `REDIS_URL` → the Upstash `rediss://` string from step 1
   - `OPENWEATHER_API_KEY` / `WEATHERAPI_KEY` → optional, only needed for `/weather/{city}/failover`
4. Render builds from the existing `Dockerfile` and deploys on its free web service plan. First deploy takes a few minutes; free-tier services spin down after 15 min of inactivity and cold-start on the next request (~30s).

`redis.from_url()` already handles Upstash's `rediss://` TLS scheme automatically — no code changes needed for the Redis side.

## Endpoints
| Endpoint | Description |
|----------|-------------|
| `GET /weather/{city}` | Current weather |
| `GET /weather/{city}/summary` | Plain-English one-line weather summary |
| `GET /weather/{city}/forecast` | 5-day forecast |
| `GET /weather/{city}/alerts` | Severe alerts |
| `GET /weather/{city}/uv` | UV index |
| `GET /weather/{city}/aqi` | Air quality index |
| `GET /weather/{city}/ml-forecast?days=N` | ML temperature forecast (N=1-14) |
| `POST /keys?tier=free\|pro` | Create an API key |
| `GET /usage` | Check quota usage (`x-api-key` header) |
| `GET /weather/{city}/failover` | Weather with automatic provider failover |
| `GET /providers/status` | Health of each weather provider |
| `GET /compare?city1=X&city2=Y` | Compare cities |
| `GET /history/{city}` | Query history |
| `GET /top` | Leaderboard |
| `GET /health` | Health check |
| `GET /version` | API version |
| `GET /ui` | Dashboard |
| `GET /docs` | Swagger UI |

## API Keys & Quotas
Every endpoint works anonymously under the existing per-IP rate limit. Optionally pass an `x-api-key` header (get one from `POST /keys`) to track usage against a daily quota instead: free tier is 200 requests/day, pro is 2000/day. Quotas reset at midnight UTC.

## Multi-Provider Failover
`/weather/{city}/failover` tries OpenWeather first, then WeatherAPI.com (set `WEATHERAPI_KEY` to enable), then Open-Meteo (free, no key, always available as a last resort). Each provider trips a circuit breaker after 3 consecutive failures and is skipped for 5 minutes. After the cooldown, one trial request is let through (half-open state) before the provider is fully trusted again — a failed trial reopens the breaker with a fresh cooldown. Check `/providers/status` to see current health (`closed`, `open`, or `half_open` per provider).

## Known Issues
See [KNOWN_ISSUES.md](KNOWN_ISSUES.md) for a tracked bug in the daily logging automation (fixed, but the history is worth knowing about).

