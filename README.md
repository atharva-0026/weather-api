# Weather API

Production-grade REST API for real-time weather data with a dark dashboard UI.

## Features
- Current weather, 5-day forecast, UV index, city comparison
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
| `GET /compare?city1=X&city2=Y` | Compare cities |
| `GET /history/{city}` | Query history |
| `GET /top` | Leaderboard |
| `GET /health` | Health check |
| `GET /ui` | Dashboard |
| `GET /docs` | Swagger UI |
