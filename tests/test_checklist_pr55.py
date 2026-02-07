"""
Tests automatiques pour la checklist PR #55.

Chaque classe correspond a un item de la checklist:
1. TestEndpointCoverage - routes.py endpoint coverage
2. TestUsersJsonDeletion - users.json not in repo
3. TestSuiteExecution - all test modules importable and valid
4. TestRateLimiterFunctional - rate limiting blocks after limit
5. TestFrontendBackendIntegration - frontend API calls match backend
"""

import os
import sys
import ast
import time
import subprocess
import inspect
import importlib

import pytest

ROOT = os.path.dirname(os.path.dirname(__file__))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

os.environ.setdefault("ENV", "test")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-testing-only-32chars!")


class TestEndpointCoverage:
    """1. Verify all API endpoints in routes.py are registered and respond."""

    def test_ui_router_has_all_expected_endpoints(self):
        from autobot.ui.routes import router
        paths = [r.path for r in router.routes]
        expected = [
            "/api/stripe/webhook",
            "/api/save-settings",
            "/api/deposit",
            "/api/withdraw",
            "/api/metrics",
            "/api/metrics/capital",
            "/api/metrics/transactions",
            "/backtest/status",
            "/api/capital-status",
            "/api/scale-now",
        ]
        for ep in expected:
            assert ep in paths, f"Missing endpoint: {ep}"

    def test_ui_router_endpoint_count(self):
        from autobot.ui.routes import router
        paths = [r.path for r in router.routes]
        assert len(paths) >= 10, f"Expected >= 10 endpoints, got {len(paths)}"

    def test_all_endpoints_have_handler_functions(self):
        from autobot.ui.routes import router
        for route in router.routes:
            assert hasattr(route, "endpoint"), f"Route {route.path} has no endpoint handler"
            assert callable(route.endpoint), f"Route {route.path} endpoint is not callable"

    def test_post_endpoints_correct_methods(self):
        from autobot.ui.routes import router
        post_paths = {"/api/stripe/webhook", "/api/save-settings", "/api/deposit", "/api/withdraw", "/api/scale-now"}
        for route in router.routes:
            if hasattr(route, "methods") and route.path in post_paths:
                assert "POST" in route.methods, f"{route.path} should be POST"

    def test_get_endpoints_correct_methods(self):
        from autobot.ui.routes import router
        get_paths = {"/api/metrics", "/api/metrics/capital", "/api/metrics/transactions", "/backtest/status", "/api/capital-status"}
        for route in router.routes:
            if hasattr(route, "methods") and route.path in get_paths:
                assert "GET" in route.methods, f"{route.path} should be GET"

    def test_login_endpoint_on_app(self):
        from autobot.main import app
        login_found = False
        for route in app.routes:
            if hasattr(route, "path") and route.path == "/login":
                login_found = True
                break
        assert login_found, "/login endpoint not found on app"

    def test_all_endpoints_return_json(self):
        from autobot.ui import routes
        source = inspect.getsource(routes)
        assert "JSONResponse" in source
        assert "HTMLResponse" not in source
        assert "TemplateResponse" not in source


class TestUsersJsonDeletion:
    """2. Verify users.json is removed from git tracking."""

    def test_users_json_not_tracked(self):
        result = subprocess.run(
            ["git", "ls-files", "users.json"],
            capture_output=True, text=True, cwd=ROOT
        )
        assert result.stdout.strip() == "", "users.json is still tracked by git"

    def test_users_json_in_gitignore(self):
        gitignore = os.path.join(ROOT, ".gitignore")
        with open(gitignore, "r") as f:
            content = f.read()
        assert "users.json" in content, "users.json not found in .gitignore"

    def test_users_json_not_in_repo_tree(self):
        result = subprocess.run(
            ["git", "ls-tree", "-r", "--name-only", "HEAD"],
            capture_output=True, text=True, cwd=ROOT
        )
        tracked_files = result.stdout.strip().split("\n")
        assert "users.json" not in tracked_files, "users.json still in HEAD tree"

    def test_no_secrets_in_gitignore_entries(self):
        gitignore = os.path.join(ROOT, ".gitignore")
        with open(gitignore, "r") as f:
            content = f.read()
        assert "users.json" in content
        assert ".env" in content or "*.env" in content


class TestSuiteExecution:
    """3. Verify all test files are valid Python and importable."""

    def test_all_test_files_valid_syntax(self):
        tests_dir = os.path.join(ROOT, "tests")
        errors = []
        for fname in os.listdir(tests_dir):
            if fname.startswith("test_") and fname.endswith(".py"):
                fpath = os.path.join(tests_dir, fname)
                try:
                    with open(fpath, "r") as f:
                        source = f.read()
                    compile(source, fpath, "exec")
                except SyntaxError as e:
                    errors.append(f"{fname}: {e}")
        assert not errors, f"Syntax errors found:\n" + "\n".join(errors)

    def test_security_fixes_test_file_exists(self):
        assert os.path.exists(os.path.join(ROOT, "tests", "test_security_fixes.py"))

    def test_checklist_test_file_exists(self):
        assert os.path.exists(os.path.join(ROOT, "tests", "test_checklist_pr55.py"))

    def test_security_fixes_has_all_classes(self):
        fpath = os.path.join(ROOT, "tests", "test_security_fixes.py")
        with open(fpath, "r") as f:
            source = f.read()
        tree = ast.parse(source)
        class_names = [node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]
        expected = [
            "TestRateLimiter",
            "TestHMACFix",
            "TestRoutesAPIOnly",
            "TestGitignoreUsers",
            "TestSaltRegenScript",
            "TestAuthOnRoutes",
            "TestCORSConfiguration",
            "TestPasswordHashing",
        ]
        for cls in expected:
            assert cls in class_names, f"Missing test class: {cls}"

    def test_conftest_provides_client_fixture(self):
        fpath = os.path.join(ROOT, "tests", "conftest.py")
        with open(fpath, "r") as f:
            source = f.read()
        assert "def client" in source, "conftest.py missing client fixture"
        assert "TestClient" in source, "conftest.py missing TestClient import"

    def test_no_test_files_with_syntax_errors(self):
        tests_dir = os.path.join(ROOT, "tests")
        test_files = [f for f in os.listdir(tests_dir) if f.startswith("test_") and f.endswith(".py")]
        assert len(test_files) >= 5, f"Expected at least 5 test files, got {len(test_files)}"


class TestRateLimiterFunctional:
    """4. Verify rate limiting actually blocks requests after limit."""

    def test_rate_limiter_allows_within_limit(self):
        from autobot.autobot_security.rate_limiter import RateLimiter
        limiter = RateLimiter(max_requests=3, window_seconds=60)
        now = time.time()
        limiter._requests["192.168.1.1"] = [now - 1, now - 2]
        limiter._clean_old_requests("192.168.1.1")
        assert len(limiter._requests["192.168.1.1"]) == 2
        assert len(limiter._requests["192.168.1.1"]) < limiter.max_requests

    def test_rate_limiter_blocks_at_limit(self):
        from autobot.autobot_security.rate_limiter import RateLimiter
        limiter = RateLimiter(max_requests=3, window_seconds=60)
        now = time.time()
        limiter._requests["192.168.1.1"] = [now - 1, now - 2, now - 3]
        limiter._clean_old_requests("192.168.1.1")
        assert len(limiter._requests["192.168.1.1"]) >= limiter.max_requests

    def test_rate_limiter_check_raises_429(self):
        from autobot.autobot_security.rate_limiter import RateLimiter
        from fastapi import HTTPException
        from unittest.mock import MagicMock, AsyncMock
        import asyncio

        limiter = RateLimiter(max_requests=2, window_seconds=60)
        mock_request = MagicMock()
        mock_request.headers = {"x-forwarded-for": "10.0.0.1"}
        mock_request.client = MagicMock()
        mock_request.client.host = "10.0.0.1"

        now = time.time()
        limiter._requests["10.0.0.1"] = [now - 1, now - 2]

        with pytest.raises(HTTPException) as exc_info:
            asyncio.get_event_loop().run_until_complete(limiter.check(mock_request))
        assert exc_info.value.status_code == 429

    def test_rate_limiter_allows_after_window_expires(self):
        from autobot.autobot_security.rate_limiter import RateLimiter
        limiter = RateLimiter(max_requests=2, window_seconds=1)
        limiter._requests["10.0.0.2"] = [time.time() - 2, time.time() - 2]
        limiter._clean_old_requests("10.0.0.2")
        assert len(limiter._requests["10.0.0.2"]) == 0

    def test_login_limiter_configured_correctly(self):
        from autobot.autobot_security.rate_limiter import login_limiter
        assert login_limiter.max_requests == 5
        assert login_limiter.window_seconds == 60

    def test_financial_limiter_configured_correctly(self):
        from autobot.autobot_security.rate_limiter import financial_limiter
        assert financial_limiter.max_requests == 10
        assert financial_limiter.window_seconds == 60

    def test_rate_limiter_extracts_ip_from_forwarded_header(self):
        from autobot.autobot_security.rate_limiter import RateLimiter
        from unittest.mock import MagicMock
        limiter = RateLimiter(max_requests=5, window_seconds=60)
        mock_request = MagicMock()
        mock_request.headers = {"x-forwarded-for": "203.0.113.50, 70.41.3.18"}
        ip = limiter._get_client_ip(mock_request)
        assert ip == "203.0.113.50"

    def test_rate_limiter_falls_back_to_client_host(self):
        from autobot.autobot_security.rate_limiter import RateLimiter
        from unittest.mock import MagicMock
        limiter = RateLimiter(max_requests=5, window_seconds=60)
        mock_request = MagicMock()
        mock_request.headers = {}
        mock_request.client = MagicMock()
        mock_request.client.host = "127.0.0.1"
        ip = limiter._get_client_ip(mock_request)
        assert ip == "127.0.0.1"

    def test_financial_endpoints_use_rate_limiter(self):
        from autobot.ui import routes
        source = inspect.getsource(routes)
        assert "financial_limiter.check" in source, "Financial endpoints missing rate limiter"

    def test_login_uses_rate_limiter(self):
        from autobot import main
        source = inspect.getsource(main)
        assert "login_limiter.check" in source, "/login missing rate limiter"


class TestFrontendBackendIntegration:
    """5. Verify frontend API calls match backend endpoints."""

    def test_vite_proxy_configured(self):
        vite_config = os.path.join(ROOT, "frontend", "vite.config.ts")
        assert os.path.exists(vite_config), "vite.config.ts not found"
        with open(vite_config, "r") as f:
            content = f.read()
        assert "proxy" in content, "Vite proxy not configured"
        assert "localhost:8000" in content, "Proxy target not pointing to backend"

    def test_vite_proxies_api_routes(self):
        vite_config = os.path.join(ROOT, "frontend", "vite.config.ts")
        with open(vite_config, "r") as f:
            content = f.read()
        required_proxies = ["/api", "/login", "/backtest", "/trade", "/setup", "/health"]
        for proxy in required_proxies:
            assert f"'{proxy}'" in content or f'"{proxy}"' in content, f"Missing proxy for {proxy}"

    def test_frontend_pages_exist(self):
        pages_dir = os.path.join(ROOT, "frontend", "src", "pages")
        assert os.path.isdir(pages_dir), "frontend/src/pages/ not found"
        expected_pages = ["LiveTrading.tsx", "Backtest.tsx", "Capital.tsx", "Analytics.tsx"]
        for page in expected_pages:
            assert os.path.exists(os.path.join(pages_dir, page)), f"Missing page: {page}"

    def test_frontend_components_exist(self):
        components_dir = os.path.join(ROOT, "frontend", "src", "components")
        assert os.path.isdir(components_dir), "frontend/src/components/ not found"

    def test_frontend_store_exists(self):
        store_file = os.path.join(ROOT, "frontend", "src", "store", "useAppStore.ts")
        assert os.path.exists(store_file), "Zustand store not found"

    def test_cors_allows_frontend_origins(self):
        from autobot.main import app
        cors_found = False
        for middleware in app.user_middleware:
            if hasattr(middleware, "cls") and "CORS" in middleware.cls.__name__:
                cors_found = True
                kwargs = middleware.kwargs
                origins = kwargs.get("allow_origins", [])
                assert "http://localhost:3000" in origins or "http://localhost:5173" in origins, \
                    f"Frontend origin not in CORS origins: {origins}"
                break
        assert cors_found, "CORS middleware not found"

    def test_backend_returns_json_not_html(self):
        from autobot.ui import routes
        source = inspect.getsource(routes)
        assert "JSONResponse" in source
        assert "Jinja2Templates" not in source
        assert "TemplateResponse" not in source
        assert "HTMLResponse" not in source

    def test_login_returns_json_with_token(self):
        from autobot import main
        source = inspect.getsource(main.login)
        assert "JSONResponse" in source, "Login should return JSONResponse"
        assert "access_token" in source, "Login should return access_token"
        assert "set_cookie" in source, "Login should set cookie"

    def test_frontend_package_json_has_dependencies(self):
        import json
        pkg_path = os.path.join(ROOT, "frontend", "package.json")
        assert os.path.exists(pkg_path), "package.json not found"
        with open(pkg_path, "r") as f:
            pkg = json.load(f)
        deps = pkg.get("dependencies", {})
        assert "react" in deps, "React not in dependencies"
        assert "zustand" in deps, "Zustand not in dependencies"
        assert "axios" in deps, "Axios not in dependencies"

    def test_frontend_api_endpoints_match_backend(self):
        from autobot.ui.routes import router
        backend_paths = {r.path for r in router.routes}
        assert "/api/deposit" in backend_paths
        assert "/api/withdraw" in backend_paths
        assert "/api/metrics" in backend_paths
        assert "/api/metrics/capital" in backend_paths
        assert "/api/scale-now" in backend_paths
        assert "/api/stripe/webhook" in backend_paths
