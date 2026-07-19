# Changelog

## [Unreleased]
- Added /weather/{city}/summary: plain-English one-line weather summary
- Documented API endpoints
- Added /weather/{city}/ml-forecast: RandomForestRegressor trained on 1yr Open-Meteo historical data per city, cyclical day-of-year + trend features, retrains daily
- Added API key issuance (POST /keys), quota tracking (GET /usage), free/pro tiers backed by Redis; optional on all weather endpoints, anonymous IP-based limiting still works unchanged
- Added multi-provider failover (/weather/{city}/failover): OpenWeather → WeatherAPI → Open-Meteo, Redis-backed circuit breaker per provider, /providers/status for health checks

## [3.0.0] - 2026-07-13
- Added /weather/{city}/aqi endpoint for air quality index
- Fixed version mismatch in /version endpoint
- Added pytest test suite and GitHub Actions CI
