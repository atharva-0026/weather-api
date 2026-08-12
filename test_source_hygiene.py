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
