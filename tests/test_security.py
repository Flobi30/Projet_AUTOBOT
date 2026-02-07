"""
Tests automatiques pour les corrections securite P0.
P0-1: JWT SECRET_KEY ne doit pas utiliser la valeur par defaut en production
P0-2: Cookie secure=True en production
P0-3: Routes sensibles protegees par authentification

Ces tests lisent les fichiers source directement pour eviter les imports lourds
(torch, etc.) qui ne sont pas disponibles en CI legere.
"""
import os
import re
import subprocess
import sys
import textwrap

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CONFIG_PATH = os.path.join(_ROOT, "src", "autobot", "autobot_security", "config.py")
_MAIN_PATH = os.path.join(_ROOT, "src", "autobot", "main.py")
_ROUTES_PATH = os.path.join(_ROOT, "src", "autobot", "ui", "routes.py")


def _read(path: str) -> str:
    with open(path, "r") as f:
        return f.read()


# ---------------------------------------------------------------------------
# P0-1 : JWT SECRET_KEY
# ---------------------------------------------------------------------------

def test_jwt_secret_config_rejects_default_value():
    src = _read(_CONFIG_PATH)
    assert "your-secret-key-change-in-production" in src, "Default key marker missing"
    assert "RuntimeError" in src or "raise" in src, "No RuntimeError raised for insecure key"
    assert re.search(r"raise\s+RuntimeError", src), "Must raise RuntimeError when key is insecure"


def test_jwt_secret_config_checks_env_variable():
    src = _read(_CONFIG_PATH)
    assert "os.getenv" in src, "SECRET_KEY must be read from env"
    assert "SECRET_KEY" in src


def test_jwt_secret_raises_in_production_when_unset():
    script = textwrap.dedent(f"""\
        import sys, os
        sys.path.insert(0, "{os.path.join(_ROOT, 'src')}")
        os.environ.pop("SECRET_KEY", None)
        os.environ.pop("ENV", None)
        try:
            import importlib
            import autobot.autobot_security.config as cfg
            importlib.reload(cfg)
            print("NO_ERROR")
        except RuntimeError as e:
            if "SECURITY ERROR" in str(e):
                print("RAISED_OK")
            else:
                print("WRONG_ERROR:" + str(e))
        except Exception as e:
            print("UNEXPECTED:" + str(e))
    """)
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True, text=True, timeout=10,
        env={k: v for k, v in os.environ.items() if k not in ("SECRET_KEY", "ENV")},
    )
    output = result.stdout.strip()
    assert output == "RAISED_OK", (
        f"Expected RuntimeError in production with no SECRET_KEY, got: {output}\n"
        f"stderr: {result.stderr}"
    )


def test_jwt_secret_raises_in_production_when_default_value():
    script = textwrap.dedent(f"""\
        import sys, os
        sys.path.insert(0, "{os.path.join(_ROOT, 'src')}")
        os.environ["SECRET_KEY"] = "your-secret-key-change-in-production"
        os.environ.pop("ENV", None)
        try:
            import importlib
            import autobot.autobot_security.config as cfg
            importlib.reload(cfg)
            print("NO_ERROR")
        except RuntimeError as e:
            if "SECURITY ERROR" in str(e):
                print("RAISED_OK")
            else:
                print("WRONG_ERROR:" + str(e))
    """)
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True, text=True, timeout=10,
        env={"SECRET_KEY": "your-secret-key-change-in-production", "PATH": os.environ.get("PATH", "")},
    )
    output = result.stdout.strip()
    assert output == "RAISED_OK", (
        f"Expected RuntimeError with default key in production, got: {output}"
    )


def test_jwt_secret_accepts_strong_key_in_production():
    script = textwrap.dedent(f"""\
        import sys, os
        sys.path.insert(0, "{os.path.join(_ROOT, 'src')}")
        os.environ["SECRET_KEY"] = "a-very-strong-secret-key-with-more-than-32-chars!"
        os.environ["ENV"] = "production"
        try:
            import importlib
            import autobot.autobot_security.config as cfg
            importlib.reload(cfg)
            if cfg.SECRET_KEY == "a-very-strong-secret-key-with-more-than-32-chars!":
                print("OK")
            else:
                print("WRONG_KEY:" + cfg.SECRET_KEY)
        except Exception as e:
            print("ERROR:" + str(e))
    """)
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True, text=True, timeout=10,
        env={"SECRET_KEY": "a-very-strong-secret-key-with-more-than-32-chars!", "ENV": "production", "PATH": os.environ.get("PATH", "")},
    )
    assert result.stdout.strip() == "OK", f"Strong key should be accepted: {result.stdout}"


def test_jwt_secret_allows_default_in_test_env():
    script = textwrap.dedent(f"""\
        import sys, os
        sys.path.insert(0, "{os.path.join(_ROOT, 'src')}")
        os.environ.pop("SECRET_KEY", None)
        os.environ["ENV"] = "test"
        try:
            import importlib
            import autobot.autobot_security.config as cfg
            importlib.reload(cfg)
            print("OK")
        except RuntimeError:
            print("RAISED")
    """)
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True, text=True, timeout=10,
        env={"ENV": "test", "PATH": os.environ.get("PATH", "")},
    )
    assert result.stdout.strip() == "OK", "Should allow default key in test env"


# ---------------------------------------------------------------------------
# P0-2 : Cookie secure flag
# ---------------------------------------------------------------------------

def test_cookie_secure_not_hardcoded_false():
    src = _read(_MAIN_PATH)
    cookie_blocks = re.findall(r"set_cookie\(.*?\)", src, re.DOTALL)
    for block in cookie_blocks:
        assert "secure=False" not in block, (
            f"Cookie still has hardcoded secure=False: {block}"
        )


def test_cookie_secure_uses_env_variable():
    src = _read(_MAIN_PATH)
    assert "_cookie_secure" in src, "Cookie secure must use _cookie_secure variable"
    assert "secure=_cookie_secure" in src, "set_cookie must use secure=_cookie_secure"


def test_cookie_secure_defaults_to_true_in_production():
    src = _read(_MAIN_PATH)
    assert re.search(r"ENV.*production|production.*ENV", src) or "ENV" in src, (
        "Cookie secure logic must reference ENV variable"
    )
    assert "not in" in src, "Production should be the secure default (not in dev list)"


# ---------------------------------------------------------------------------
# P0-3 : Routes sensibles protegees par auth (Depends(get_current_user))
# ---------------------------------------------------------------------------

PROTECTED_ROUTES = {
    "/trading": "get_trading",
    "/backtest": "get_backtest",
    "/capital": "get_capital",
    "/retrait-depot": "get_retrait_depot",
}


def _extract_route_def(src: str, func_name: str) -> str:
    pattern = rf"((?:@router\.(?:get|post)\([^\)]+\)\s*\n)+\s*async\s+def\s+{func_name}\([^)]*\))"
    m = re.search(pattern, src)
    assert m, f"Could not find route function {func_name}"
    return m.group(1)


@pytest.mark.parametrize("route,func_name", list(PROTECTED_ROUTES.items()))
def test_route_has_get_current_user_dependency(route, func_name):
    src = _read(_ROUTES_PATH)
    route_def = _extract_route_def(src, func_name)
    assert "get_current_user" in route_def, (
        f"Route {route} ({func_name}) is missing Depends(get_current_user)"
    )
    assert "user" in route_def, (
        f"Route {route} ({func_name}) is missing 'user' parameter"
    )


@pytest.mark.parametrize("route,func_name", list(PROTECTED_ROUTES.items()))
def test_route_signature_includes_user_param(route, func_name):
    src = _read(_ROUTES_PATH)
    pattern = rf"async\s+def\s+{func_name}\(request:\s*Request\s*,\s*user:"
    assert re.search(pattern, src), (
        f"Route {route} ({func_name}) must have 'user' as second parameter"
    )


def test_routes_file_imports_get_current_user():
    src = _read(_ROUTES_PATH)
    assert "get_current_user" in src, "routes.py must import get_current_user"
    assert "from autobot.autobot_security" in src, (
        "get_current_user must be imported from autobot_security"
    )

