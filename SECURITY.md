# Security Policy

This is a personal/academic project, not a funded product with a
dedicated security team — but reports are still welcome and taken
seriously.

## Reporting a vulnerability

Please open a GitHub issue or contact the repo owner directly rather
than disclosing publicly first, especially for anything involving
credential leakage or remote code execution.

## Known dependency findings

Dependencies are periodically checked with `pip-audit`. As of the last
check, no known vulnerabilities were found in `requirements.txt`.

## Notes on this service

- API keys (`/keys` endpoint) are Redis-backed and rate-limited; treat
  `.env` and any real Redis instance credentials as secrets — never
  commit them (see `.gitignore`).
- Provider API keys (OpenWeather, WeatherAPI) should be scoped to
  read-only weather data access where the provider allows it.
