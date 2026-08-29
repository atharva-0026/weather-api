"""
Static checks on source files that don't need a running server or
Redis — quick guardrails against regressions found via bandit.
"""
import os
import re

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _read(filename):
    with open(os.path.join(BASE_DIR, filename), encoding="utf-8") as f:
        return f.read()


def test_no_bare_except_pass_in_main():
    """Regression test: refresh_cache() previously had a bare
    `except: pass` (bandit B110) that silently swallowed every
    exception, including KeyboardInterrupt/SystemExit, with no logging.
    Must be `except Exception:` with a logged failure."""
    content = _read("main.py")
    assert not re.search(r"except\s*:\s*\n\s*pass", content), (
        "main.py must not contain a bare `except: pass` block"
    )
    assert "except Exception:" in content
    assert "logging.warning" in content or "logging.error" in content


def test_no_utcnow_deprecation_regressions():
    """Regression test: datetime.utcnow() is deprecated; all of
    auth.py, main.py, providers.py were migrated to
    datetime.now(timezone.utc). Guard against it creeping back in."""
    for filename in ["auth.py", "main.py", "providers.py"]:
        content = _read(filename)
        assert "datetime.utcnow()" not in content, f"{filename} still uses deprecated datetime.utcnow()"


def test_readme_documents_every_endpoint():
    """Regression test: the README endpoint table was previously split
    in half by prose, silently dropping /compare, /history, /top,
    /health, /ui, /docs from the table, and never listed /version or
    /weather/{city}/summary at all. Every @app.get/@app.post path in
    main.py must appear somewhere in README.md."""
    main_content = _read("main.py")
    readme_content = _read("README.md")

    paths = re.findall(r'@app\.(?:get|post)\("([^"]+)"', main_content)
    assert paths, "expected to find at least one route in main.py"

    missing = []
    for path in paths:
        # Convert /weather/{city}/uv -> /weather/{city}/uv (already
        # matches README's {city} placeholder style); just check the
        # literal path segment appears somewhere in the README.
        if path not in readme_content:
            missing.append(path)

    assert not missing, f"Endpoints missing from README.md: {missing}"


def test_daily_log_uses_correct_weather_url_shape():
    """Regression test: daily_log.py previously called
    /weather?city=Pune (query param), but the actual route in main.py
    is path-based (/weather/{city}). Every single day since launch
    silently logged {"error": 404} instead of real weather data. Must
    use the path form: /weather/<city>."""
    content = _read("daily_log.py")
    assert "params={\"city\"" not in content, (
        "daily_log.py must not use the query-param form ?city=... — "
        "the actual route is path-based, see main.py"
    )
    assert "/weather/Pune" in content or "/weather/{" in content


def test_docker_compose_env_file_is_optional():
    """Regression test: docker-compose.yml's `env_file: .env` previously
    hard-failed `docker compose up --build` on a fresh clone (no .env
    exists until you copy .env.example), directly contradicting the
    README's one-line run instructions. Must use the long-form
    `required: false` syntax."""
    content = _read("docker-compose.yml")
    assert "required: false" in content or "required: False" in content, (
        "docker-compose.yml's env_file must be optional (required: false) "
        "so a fresh clone with no .env doesn't hard-fail"
    )
