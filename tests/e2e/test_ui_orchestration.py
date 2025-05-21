"""
Tests E2E pour l'orchestration 100% UI d'AUTOBOT.
Ce test vérifie le workflow complet : Configuration → Auto-backtest → Live + backtest continu.
"""

import pytest
from playwright.sync_api import Page, expect
import time
import os
from datetime import datetime

TEST_URL = os.environ.get("TEST_URL", "http://localhost:8000")
TIMEOUT = 30000  # 30 secondes

@pytest.fixture(scope="function")
def setup_test_data():
    """Prépare les données de test."""
    return {
        "api_keys": {
            "alpha": "test_alpha_key_" + datetime.now().strftime("%Y%m%d%H%M%S"),
            "twelve": "test_twelve_key_" + datetime.now().strftime("%Y%m%d%H%M%S"),
            "fred": "test_fred_key_" + datetime.now().strftime("%Y%m%d%H%M%S"),
            "news": "test_news_key_" + datetime.now().strftime("%Y%m%d%H%M%S"),
            "shopify": "test_shopify_key_" + datetime.now().strftime("%Y%m%d%H%M%S"),
            "ollama": "test_ollama_key_" + datetime.now().strftime("%Y%m%d%H%M%S"),
        },
        "licence": "TEST-LICENCE-KEY-" + datetime.now().strftime("%Y%m%d%H%M%S"),
        "jwt": {
            "secret": "test_jwt_secret_" + datetime.now().strftime("%Y%m%d%H%M%S"),
            "algorithm": "HS256"
        },
        "admin": {
            "user": "admin_test",
            "password": "password_test_secure"
        }
    }

def test_setup_page(page: Page, setup_test_data):
    """
    Teste la page de configuration initiale.
    """
    page.goto(f"{TEST_URL}/setup")
    
    expect(page.locator("h1")).to_contain_text("Configuration initiale")
    
    page.fill("#alpha_api_key", setup_test_data["api_keys"]["alpha"])
    page.fill("#twelve_api_key", setup_test_data["api_keys"]["twelve"])
    page.fill("#fred_api_key", setup_test_data["api_keys"]["fred"])
    page.fill("#news_api_key", setup_test_data["api_keys"]["news"])
    page.fill("#shopify_api_key", setup_test_data["api_keys"]["shopify"])
    page.fill("#ollama_api_key", setup_test_data["api_keys"]["ollama"])
    page.fill("#licence_key", setup_test_data["licence"])
    page.fill("#jwt_secret_key", setup_test_data["jwt"]["secret"])
    page.select_option("#jwt_algorithm", setup_test_data["jwt"]["algorithm"])
    page.fill("#admin_user", setup_test_data["admin"]["user"])
    page.fill("#admin_password", setup_test_data["admin"]["password"])
    
    with page.expect_response(lambda response: response.url.endswith("/api/setup") and response.status == 200) as response_info:
        page.click("button[type='submit']")
    
    expect(page.locator(".status-message.success")).to_be_visible(timeout=TIMEOUT)
    expect(page.locator(".status-message.success")).to_contain_text("Configuration validée")
    
    page.wait_for_url(f"{TEST_URL}/backtests", timeout=TIMEOUT)

def test_backtests_page(page: Page):
    """
    Teste la page des backtests automatiques.
    """
    page.goto(f"{TEST_URL}/backtests")
    
    expect(page.locator("h1")).to_contain_text("Backtests Automatiques")
    
    page.fill("#min_sharpe", "1.2")
    page.fill("#max_drawdown", "20")
    page.fill("#min_pnl", "5")
    page.check("#auto_live")
    
    with page.expect_response(lambda response: response.url.endswith("/api/backtest/thresholds") and response.status == 200) as response_info:
        page.click("#update-thresholds")
    
    expect(page.locator("#backtests-table tbody tr")).to_have_count(lambda count: count > 0, timeout=TIMEOUT)
    
    max_wait_time = 60  # secondes
    for i in range(max_wait_time):
        if page.locator("#overall-status").inner_text() == "🚀 Live":
            break
        time.sleep(1)
    
    expect(page.locator("#overall-status")).to_contain_text("🚀 Live", timeout=TIMEOUT)
    
    page.wait_for_url(f"{TEST_URL}/operations", timeout=TIMEOUT)

def test_operations_page(page: Page):
    """
    Teste la page des opérations (trading live + backtests continus).
    """
    page.goto(f"{TEST_URL}/operations")
    
    expect(page.locator("h1")).to_contain_text("Opérations")
    
    expect(page.locator(".trading-status")).to_contain_text("Actif", timeout=TIMEOUT)
    
    expect(page.locator("#toggle-backtest")).to_be_checked()
    
    with page.expect_response(lambda response: response.url.endswith("/api/backtest/continuous") and response.status == 200) as response_info:
        page.click("#toggle-backtest")
    
    expect(page.locator("#toggle-backtest")).not_to_be_checked()
    
    with page.expect_response(lambda response: response.url.endswith("/api/backtest/continuous") and response.status == 200) as response_info:
        page.click("#toggle-backtest")
    
    expect(page.locator("#toggle-backtest")).to_be_checked()

def test_ghosting_page(page: Page):
    """
    Teste la page de ghosting.
    """
    page.goto(f"{TEST_URL}/ghosting")
    
    expect(page.locator("h1")).to_contain_text("Ghosting")
    
    page.fill("#max_instances", "5")
    page.select_option("#evasion_mode", "combined")
    page.select_option("#instance_type", "all")
    
    with page.expect_response(lambda response: response.url.endswith("/api/ghosting/config") and response.status == 200) as response_info:
        page.click("button[type='submit']")
    
    expect(page.locator(".alert-success")).to_be_visible(timeout=TIMEOUT)
    expect(page.locator(".alert-success")).to_contain_text("Configuration appliquée")
    
    expect(page.locator("#instances-table tbody tr")).to_have_count(lambda count: count > 0, timeout=TIMEOUT)

def test_licence_page(page: Page, setup_test_data):
    """
    Teste la page de licence.
    """
    page.goto(f"{TEST_URL}/licence")
    
    expect(page.locator("h1")).to_contain_text("Gestion de Licence")
    
    expect(page.locator("#license-status-text")).to_contain_text("Valide", timeout=TIMEOUT)
    
    page.fill("#license_key", "NEW-TEST-LICENCE-" + datetime.now().strftime("%Y%m%d%H%M%S"))
    
    with page.expect_response(lambda response: response.url.endswith("/api/license/apply") and response.status == 200) as response_info:
        page.click("button[type='submit']")
    
    expect(page.locator("#license-status-text")).to_contain_text("Valide", timeout=TIMEOUT)
    
    expect(page.locator("#validation-history tbody tr")).to_have_count(lambda count: count > 0, timeout=TIMEOUT)

def test_logs_page(page: Page):
    """
    Teste la page des logs.
    """
    page.goto(f"{TEST_URL}/logs")
    
    expect(page.locator("h1")).to_contain_text("Logs & Monitoring")
    
    expect(page.locator("#logs-table tbody tr")).to_have_count(lambda count: count > 0, timeout=TIMEOUT)
    
    page.click(".filter-btn[data-filter='backtest']")
    time.sleep(1)  # Attendre le filtrage
    
    expect(page.locator(".active-filter")).to_contain_text("Backtest")
    
    with page.expect_download() as download_info:
        page.click("#download-csv")
    download = download_info.value
    
    assert download.suggested_filename.startswith("autobot_logs_")

def test_complete_workflow(page: Page, setup_test_data):
    """
    Teste le workflow complet : Configuration → Auto-backtest → Live + backtest continu.
    """
    test_setup_page(page, setup_test_data)
    
    test_backtests_page(page)
    
    test_operations_page(page)
    
    test_ghosting_page(page)
    
    test_licence_page(page, setup_test_data)
    
    test_logs_page(page)
    
    page.goto(f"{TEST_URL}/operations")
    expect(page.locator(".trading-status")).to_contain_text("Actif", timeout=TIMEOUT)
    expect(page.locator("#toggle-backtest")).to_be_checked()
