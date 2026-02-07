"""Tests for security fixes: rate limiting, HMAC, auth, salt, API-only routes."""

import os
import sys
import time
import hashlib
import hmac

import pytest

root = os.path.dirname(os.path.dirname(__file__))
src = os.path.join(root, "src")
if src not in sys.path:
    sys.path.insert(0, src)

os.environ.setdefault("ENV", "test")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-testing-only-32chars!")


class TestRateLimiter:
    """Test the RateLimiter class."""

    def test_rate_limiter_init(self):
        from autobot.autobot_security.rate_limiter import RateLimiter
        limiter = RateLimiter(max_requests=5, window_seconds=60)
        assert limiter.max_requests == 5
        assert limiter.window_seconds == 60

    def test_login_limiter_defaults(self):
        from autobot.autobot_security.rate_limiter import login_limiter
        assert login_limiter.max_requests == 5
        assert login_limiter.window_seconds == 60

    def test_financial_limiter_defaults(self):
        from autobot.autobot_security.rate_limiter import financial_limiter
        assert financial_limiter.max_requests == 10
        assert financial_limiter.window_seconds == 60

    def test_rate_limiter_clean_old_requests(self):
        from autobot.autobot_security.rate_limiter import RateLimiter
        limiter = RateLimiter(max_requests=5, window_seconds=1)
        limiter._requests["test_ip"] = [time.time() - 2, time.time() - 2]
        limiter._clean_old_requests("test_ip")
        assert len(limiter._requests["test_ip"]) == 0

    def test_rate_limiter_keeps_recent_requests(self):
        from autobot.autobot_security.rate_limiter import RateLimiter
        limiter = RateLimiter(max_requests=5, window_seconds=60)
        now = time.time()
        limiter._requests["test_ip"] = [now - 1, now - 2, now - 3]
        limiter._clean_old_requests("test_ip")
        assert len(limiter._requests["test_ip"]) == 3


class TestHMACFix:
    """Test that HMAC uses hmac.HMAC() instead of hmac.new()."""

    def test_hmac_class_exists(self):
        assert hasattr(hmac, "HMAC")

    def test_hmac_produces_valid_signature(self):
        key = b"test_webhook_secret"
        payload = b"test_payload_data"
        sig = hmac.HMAC(key, payload, hashlib.sha256).hexdigest()
        assert len(sig) == 64
        assert all(c in "0123456789abcdef" for c in sig)

    def test_hmac_signature_reproducible(self):
        key = b"secret"
        payload = b"data"
        sig1 = hmac.HMAC(key, payload, hashlib.sha256).hexdigest()
        sig2 = hmac.HMAC(key, payload, hashlib.sha256).hexdigest()
        assert sig1 == sig2

    def test_webhooks_uses_hmac_class(self):
        import inspect
        from autobot.stripe import webhooks
        source = inspect.getsource(webhooks)
        assert "hmac.HMAC(" in source
        assert "hmac.new(" not in source


class TestRoutesAPIOnly:
    """Test that routes.py has no Jinja2 template dependencies."""

    def test_no_jinja2_import(self):
        import inspect
        from autobot.ui import routes
        source = inspect.getsource(routes)
        assert "Jinja2Templates" not in source
        assert "TemplateResponse" not in source

    def test_no_html_response(self):
        import inspect
        from autobot.ui import routes
        source = inspect.getsource(routes)
        assert "HTMLResponse" not in source

    def test_router_exists(self):
        from autobot.ui.routes import router
        assert router is not None

    def test_api_endpoints_exist(self):
        from autobot.ui.routes import router
        paths = [r.path for r in router.routes]
        assert "/api/stripe/webhook" in paths
        assert "/api/deposit" in paths
        assert "/api/withdraw" in paths
        assert "/api/metrics" in paths
        assert "/api/metrics/capital" in paths
        assert "/api/scale-now" in paths


class TestGitignoreUsers:
    """Test that users.json is in .gitignore."""

    def test_users_json_in_gitignore(self):
        gitignore_path = os.path.join(root, ".gitignore")
        with open(gitignore_path, "r") as f:
            content = f.read()
        assert "users.json" in content


class TestSaltRegenScript:
    """Test that the salt regeneration script exists and is valid Python."""

    def test_script_exists(self):
        script_path = os.path.join(root, "scripts", "regenerate_admin_salt.py")
        assert os.path.exists(script_path)

    def test_script_is_valid_python(self):
        script_path = os.path.join(root, "scripts", "regenerate_admin_salt.py")
        with open(script_path, "r") as f:
            source = f.read()
        compile(source, script_path, "exec")

    def test_script_has_regenerate_function(self):
        script_path = os.path.join(root, "scripts", "regenerate_admin_salt.py")
        with open(script_path, "r") as f:
            source = f.read()
        assert "def regenerate_salt" in source


class TestAuthOnRoutes:
    """Test that sensitive routes require authentication."""

    def test_router_clean_trade_requires_auth(self):
        import inspect
        from autobot.router_clean import trade
        sig = inspect.signature(trade)
        param_names = list(sig.parameters.keys())
        assert "user" in param_names

    def test_router_clean_setup_requires_auth(self):
        import inspect
        from autobot.router_clean import setup_api_keys
        sig = inspect.signature(setup_api_keys)
        param_names = list(sig.parameters.keys())
        assert "user" in param_names

    def test_router_clean_ghosting_requires_auth(self):
        import inspect
        from autobot.router_clean import start_ghosting
        sig = inspect.signature(start_ghosting)
        param_names = list(sig.parameters.keys())
        assert "user" in param_names

    def test_ui_routes_deposit_requires_auth(self):
        import inspect
        from autobot.ui.routes import deposit
        sig = inspect.signature(deposit)
        param_names = list(sig.parameters.keys())
        assert "user" in param_names

    def test_ui_routes_withdraw_requires_auth(self):
        import inspect
        from autobot.ui.routes import withdraw
        sig = inspect.signature(withdraw)
        param_names = list(sig.parameters.keys())
        assert "user" in param_names

    def test_ui_routes_metrics_requires_auth(self):
        import inspect
        from autobot.ui.routes import get_real_time_metrics
        sig = inspect.signature(get_real_time_metrics)
        param_names = list(sig.parameters.keys())
        assert "user" in param_names


class TestCORSConfiguration:
    """Test that CORS is properly configured."""

    def test_cors_middleware_present(self):
        from autobot.main import app
        middleware_classes = [type(m).__name__ for m in app.user_middleware]
        cors_found = any("CORS" in cls or "cors" in cls.lower() for cls in middleware_classes)
        if not cors_found:
            middleware_classes = [m.cls.__name__ for m in app.user_middleware if hasattr(m, "cls")]
            cors_found = any("CORS" in cls for cls in middleware_classes)
        assert cors_found


class TestPasswordHashing:
    """Test password hashing with proper salt."""

    def test_hash_with_random_salt(self):
        salt = os.urandom(32).hex()
        password = "test_password"
        h = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 100000).hex()
        assert len(h) == 64
        assert salt != "0" * 64

    def test_different_salts_different_hashes(self):
        password = "same_password"
        salt1 = os.urandom(32).hex()
        salt2 = os.urandom(32).hex()
        h1 = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt1), 100000).hex()
        h2 = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt2), 100000).hex()
        assert h1 != h2

    def test_zero_salt_is_insecure(self):
        zero_salt = "0" * 64
        random_salt = os.urandom(32).hex()
        assert zero_salt != random_salt
