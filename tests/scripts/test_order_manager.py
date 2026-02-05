"""
Tests for scripts/order_manager.py - Phase 1 Task 4/7.

Tests unitaires pour le placement d'ordres LIMIT sur Kraken.
Les appels API sont mockés pour éviter les appels réels.
"""

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src', 'grid_engine'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))

from order_manager import (
    KrakenOrder,
    create_kraken_client,
    get_btc_eur_price,
    calculate_grid_level_0,
    check_eur_balance,
    place_buy_order,
    verify_open_order,
    query_order,
    KRAKEN_PAIR_CCXT,
)


class TestKrakenOrder:
    def test_creation(self):
        order = KrakenOrder(
            order_id="GRID-L0-1234567890",
            exchange_order_id="OXXXXX-XXXXX-XXXXXX",
            pair="BTC/EUR",
            side="buy",
            order_type="limit",
            price=51588.1,
            volume_btc=0.000646,
            volume_eur=33.33,
            level_id=0,
        )
        assert order.order_id == "GRID-L0-1234567890"
        assert order.exchange_order_id == "OXXXXX-XXXXX-XXXXXX"
        assert order.pair == "BTC/EUR"
        assert order.side == "buy"
        assert order.order_type == "limit"
        assert order.price == 51588.1
        assert order.volume_btc == 0.000646
        assert order.volume_eur == 33.33
        assert order.level_id == 0
        assert order.status == "open"

    def test_to_dict(self):
        order = KrakenOrder(
            order_id="GRID-L0-123",
            exchange_order_id="OTXID-123",
            pair="BTC/EUR",
            side="buy",
            order_type="limit",
            price=51000.0,
            volume_btc=0.0006,
            volume_eur=30.6,
            level_id=0,
        )
        d = order.to_dict()
        assert d["order_id"] == "GRID-L0-123"
        assert d["exchange_order_id"] == "OTXID-123"
        assert d["pair"] == "BTC/EUR"
        assert d["side"] == "buy"
        assert d["order_type"] == "limit"
        assert d["price"] == 51000.0
        assert d["volume_btc"] == 0.0006
        assert d["volume_eur"] == 30.6
        assert d["level_id"] == 0
        assert d["status"] == "open"
        assert "created_at" in d

    def test_default_status(self):
        order = KrakenOrder(
            order_id="test",
            exchange_order_id="test",
            pair="BTC/EUR",
            side="buy",
            order_type="limit",
            price=50000.0,
            volume_btc=0.001,
            volume_eur=50.0,
            level_id=0,
        )
        assert order.status == "open"
        assert isinstance(order.created_at, datetime)


class TestGetBtcEurPrice:
    def test_returns_price_data(self):
        mock_exchange = MagicMock()
        mock_exchange.fetch_ticker.return_value = {
            'last': 55000.0,
            'bid': 54990.0,
            'ask': 55010.0,
        }
        result = get_btc_eur_price(mock_exchange)
        assert result["price"] == 55000.0
        assert result["bid"] == 54990.0
        assert result["ask"] == 55010.0
        mock_exchange.fetch_ticker.assert_called_once_with(KRAKEN_PAIR_CCXT)


class TestCalculateGridLevel0:
    def test_level_0_is_lowest(self):
        level = calculate_grid_level_0(55000.0)
        assert level.level_id == 0
        assert level.side.value == "buy"
        assert level.price < 55000.0

    def test_level_0_price_within_range(self):
        center = 55000.0
        level = calculate_grid_level_0(center)
        lower_bound = center * (1 - 0.07)
        assert level.price >= lower_bound
        assert level.price < center

    def test_level_0_has_allocated_capital(self):
        level = calculate_grid_level_0(55000.0)
        expected_capital = 500.0 / 15
        assert abs(level.allocated_capital - expected_capital) < 0.01

    def test_level_0_quantity_positive(self):
        level = calculate_grid_level_0(55000.0)
        assert level.quantity > 0


class TestCheckEurBalance:
    def test_sufficient_funds(self):
        mock_exchange = MagicMock()
        mock_exchange.fetch_balance.return_value = {
            'free': {'EUR': 100.0},
            'total': {'EUR': 150.0},
        }
        result = check_eur_balance(mock_exchange, 33.33)
        assert result["available"] == 100.0
        assert result["total"] == 150.0
        assert result["required"] == 33.33
        assert result["sufficient"] is True

    def test_insufficient_funds(self):
        mock_exchange = MagicMock()
        mock_exchange.fetch_balance.return_value = {
            'free': {'EUR': 10.0},
            'total': {'EUR': 10.0},
        }
        result = check_eur_balance(mock_exchange, 33.33)
        assert result["sufficient"] is False

    def test_zero_balance(self):
        mock_exchange = MagicMock()
        mock_exchange.fetch_balance.return_value = {
            'free': {},
            'total': {},
        }
        result = check_eur_balance(mock_exchange, 33.33)
        assert result["available"] == 0.0
        assert result["sufficient"] is False


class TestPlaceBuyOrder:
    def test_place_order_success(self):
        mock_exchange = MagicMock()
        mock_exchange.create_order.return_value = {
            'id': 'OABCDE-FGHIJ-KLMNOP',
            'status': 'open',
            'info': {
                'descr': {
                    'order': 'buy 0.00064600 XBTEUR @ limit 51588.1'
                }
            },
        }
        order = place_buy_order(
            exchange=mock_exchange,
            price=51588.1,
            volume_btc=0.000646,
            level_id=0,
        )
        assert order.exchange_order_id == 'OABCDE-FGHIJ-KLMNOP'
        assert order.side == "buy"
        assert order.order_type == "limit"
        assert order.price == 51588.1
        assert order.volume_btc == 0.000646
        assert order.level_id == 0
        assert order.status == "open"
        mock_exchange.create_order.assert_called_once_with(
            symbol=KRAKEN_PAIR_CCXT,
            type='limit',
            side='buy',
            amount=0.000646,
            price=51588.1,
        )

    def test_place_order_volume_rounding(self):
        mock_exchange = MagicMock()
        mock_exchange.create_order.return_value = {
            'id': 'OTEST-123',
            'status': 'open',
            'info': {'descr': {'order': ''}},
        }
        order = place_buy_order(
            exchange=mock_exchange,
            price=51588.123456,
            volume_btc=0.00064612345678,
            level_id=0,
        )
        assert order.volume_btc == 0.00064612
        assert order.price == 51588.1

    def test_order_id_format(self):
        mock_exchange = MagicMock()
        mock_exchange.create_order.return_value = {
            'id': 'OTEST',
            'status': 'open',
            'info': {'descr': {'order': ''}},
        }
        order = place_buy_order(
            exchange=mock_exchange,
            price=50000.0,
            volume_btc=0.001,
            level_id=3,
        )
        assert order.order_id.startswith("GRID-L3-")


class TestVerifyOpenOrder:
    def test_order_found(self):
        mock_exchange = MagicMock()
        mock_exchange.fetch_open_orders.return_value = [
            {
                'id': 'OABCDE-123',
                'status': 'open',
                'type': 'limit',
                'side': 'buy',
                'price': 51588.1,
                'amount': 0.000646,
                'filled': 0.0,
                'remaining': 0.000646,
                'datetime': '2026-02-05T18:00:00Z',
            },
        ]
        result = verify_open_order(mock_exchange, 'OABCDE-123')
        assert result["found"] is True
        assert result["order_info"]["id"] == 'OABCDE-123'
        assert result["order_info"]["status"] == 'open'
        assert result["open_orders_count"] == 1

    def test_order_not_found(self):
        mock_exchange = MagicMock()
        mock_exchange.fetch_open_orders.return_value = [
            {
                'id': 'OTHER-ORDER',
                'status': 'open',
                'type': 'limit',
                'side': 'buy',
                'price': 49000.0,
                'amount': 0.001,
                'filled': 0.0,
                'remaining': 0.001,
                'datetime': '2026-02-05T17:00:00Z',
            },
        ]
        result = verify_open_order(mock_exchange, 'OABCDE-123')
        assert result["found"] is False
        assert result["order_info"] is None

    def test_empty_open_orders(self):
        mock_exchange = MagicMock()
        mock_exchange.fetch_open_orders.return_value = []
        result = verify_open_order(mock_exchange, 'OABCDE-123')
        assert result["found"] is False
        assert result["open_orders_count"] == 0


class TestQueryOrder:
    def test_query_success(self):
        mock_exchange = MagicMock()
        mock_exchange.fetch_order.return_value = {
            'id': 'OABCDE-123',
            'status': 'open',
            'type': 'limit',
            'side': 'buy',
            'price': 51588.1,
            'amount': 0.000646,
            'filled': 0.0,
            'remaining': 0.000646,
            'cost': 0.0,
            'fee': {'cost': 0.0, 'currency': 'EUR'},
            'datetime': '2026-02-05T18:00:00Z',
        }
        result = query_order(mock_exchange, 'OABCDE-123')
        assert result["id"] == 'OABCDE-123'
        assert result["status"] == 'open'
        assert result["price"] == 51588.1
        assert result["amount"] == 0.000646
        mock_exchange.fetch_order.assert_called_once_with(
            'OABCDE-123', KRAKEN_PAIR_CCXT
        )


class TestCreateKrakenClient:
    @patch.dict(os.environ, {"KRAKEN_API_KEY": "test_key", "KRAKEN_API_SECRET": "test_secret"})
    @patch('order_manager.ccxt.kraken')
    def test_creates_client(self, mock_kraken_class):
        mock_instance = MagicMock()
        mock_kraken_class.return_value = mock_instance
        client = create_kraken_client()
        assert client == mock_instance
        mock_kraken_class.assert_called_once_with({
            'apiKey': 'test_key',
            'secret': 'test_secret',
            'enableRateLimit': True,
        })

    @patch.dict(os.environ, {"KRAKEN_API_KEY": "", "KRAKEN_API_SECRET": ""})
    def test_missing_keys_exits(self):
        with pytest.raises(SystemExit):
            create_kraken_client()
