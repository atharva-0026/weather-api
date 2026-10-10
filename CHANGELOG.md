# Changelog

## [Unreleased]
- Redesigned `/ui`: condition-aware hero card (icon + gradient by weather type, day/night), sunrise/sunset and city-local times, light/dark theme toggle, recent-search chips, `?city=` deep links, `/` keyboard shortcut, skeleton loading, area chart for the ML forecast, copy-to-clipboard for new API keys, responsive mobile layout
- Fixed stored XSS in `/ui`: leaderboard city names (typed by other visitors) and `/compare` keys were rendered via `innerHTML` unescaped; all API-derived strings now go through `esc()`
- Added `Makefile` (`make run`, `make test`, `make help`, …)
- Open-Meteo fallback now returns a real weather description (WMO `weather_code` mapping) instead of "—"
- Added /weather/{city}/summary: plain-English one-line weather summary
- Documented API endpoints
- Added /weather/{city}/ml-forecast: RandomForestRegressor trained on 1yr Open-Meteo historical data per city, cyclical day-of-year + trend features, retrains daily
- Added API key issuance (POST /keys), quota tracking (GET /usage), free/pro tiers backed by Redis; optional on all weather endpoints, anonymous IP-based limiting still works unchanged
- Added multi-provider failover (/weather/{city}/failover): OpenWeather → WeatherAPI → Open-Meteo, Redis-backed circuit breaker per provider, /providers/status for health checks

## [3.0.0] - 2026-07-13
- Added /weather/{city}/aqi endpoint for air quality index
- Fixed version mismatch in /version endpoint
- Added pytest test suite and GitHub Actions CI
