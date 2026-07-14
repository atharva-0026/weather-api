# Weather API

**Live:** https://weather-api-production-fc6a.up.railway.app/ui

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
docker compose up --build
```

## Endpoints
| Endpoint | Description |
|----------|-------------|
| `GET /weather/{city}` | Current weather |
| `GET /weather/{city}/forecast` | 5-day forecast |
| `GET /weather/{city}/alerts` | Severe alerts |
| `GET /weather/{city}/uv` | UV index |
| `GET /weather/{city}/aqi` | Air quality index |
| `GET /weather/{city}/ml-forecast?days=N` | ML temperature forecast (N=1-14) |
| `POST /keys?tier=free\|pro` | Create an API key |
| `GET /usage` | Check quota usage (`x-api-key` header) |
| `GET /weather/{city}/failover` | Weather with automatic provider failover |
| `GET /providers/status` | Health of each weather provider |

## API Keys & Quotas
Every endpoint works anonymously under the existing per-IP rate limit. Optionally pass an `x-api-key` header (get one from `POST /keys`) to track usage against a daily quota instead: free tier is 200 requests/day, pro is 2000/day. Quotas reset at midnight UTC.

## Multi-Provider Failover
`/weather/{city}/failover` tries OpenWeather first, then WeatherAPI.com (set `WEATHERAPI_KEY` to enable), then Open-Meteo (free, no key, always available as a last resort). Each provider trips a circuit breaker after 3 consecutive failures and is skipped for 5 minutes so a dead provider doesn't add latency to every request. Check `/providers/status` to see current health.
| `GET /compare?city1=X&city2=Y` | Compare cities |
| `GET /history/{city}` | Query history |
| `GET /top` | Leaderboard |
| `GET /health` | Health check |
| `GET /ui` | Dashboard |
| `GET /docs` | Swagger UI |

