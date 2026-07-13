# Changelog

## [Unreleased]
- Documented API endpoints
- Added /weather/{city}/ml-forecast: RandomForestRegressor trained on 1yr Open-Meteo historical data per city, cyclical day-of-year + trend features, retrains daily

## [3.0.0] - 2026-07-13
- Added /weather/{city}/aqi endpoint for air quality index
- Fixed version mismatch in /version endpoint
- Added pytest test suite and GitHub Actions CI
