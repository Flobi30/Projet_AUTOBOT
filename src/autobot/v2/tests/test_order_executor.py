"""
Tests unitaires pour OrderExecutor avec mock de l'API Kraken
"""

import unittest
import json
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

import sys
sys.path.insert(0, 'src')

from autobot.v2.order_executor import OrderExecutor, OrderSide, OrderResult, get_order_executor, reset_order_executor


class TestOrderExecutor(unittest.TestCase):
    """Tests pour OrderExecutor"""
    
    def setUp(self):
        """Reset singleton avant chaque test"""
        reset_order_executor()
        self.api_key = "test_key"
        self.api_secret = "test_secret"
        
    @patch('autobot.v2.order_executor.krakenex')
    def test_execute_market_order_success(self, mock_krakenex):
        """Test exécution ordre market réussi"""
        # Setup mock
        mock_api = MagicMock()
        mock_krakenex.API.return_value = mock_api
        mock_api.query_private.return_value = {
            'result': {
                'txid': ['TEST-TXID-123'],
                'descr': {'order': 'buy 0.01 XXBTZEUR @ market'}
            }
        }
        mock_api.query_private.side_effect = [
            # AddOrder response
            {'result': {'txid': ['TEST-TXID-123']}},
            # QueryOrders response (closed)
            {'result': {'TEST-TXID-123': {
                'status': 'closed',
                'vol_exec': '0.01',
                'price': '50000.0',
                'avg_price': '50100.0',
                'fee': '0.52'
            }}}
        ]
        
        executor = OrderExecutor(self.api_key, self.api_secret)
        
        # Test
        result = executor.execute_market_order('XXBTZEUR', OrderSide.BUY, 0.01)
        
        # Vérifications
        self.assertTrue(result.success)
        self.assertEqual(result.txid, 'TEST-TXID-123')
        self.assertEqual(result.executed_volume, 0.01)
        self.assertEqual(result.executed_price, 50100.0)
        self.assertEqual(result.fees, 0.52)
        
    @patch('autobot.v2.order_executor.krakenex')
    def test_execute_market_order_api_error(self, mock_krakenex):
        """Test gestion erreur API"""
        mock_api = MagicMock()
        mock_krakenex.API.return_value = mock_api
        mock_api.query_private.return_value = {
            'error': ['EOrder:Insufficient funds']
        }
        
        executor = OrderExecutor(self.api_key, self.api_secret)
        result = executor.execute_market_order('XXBTZEUR', OrderSide.BUY, 100.0)
        
        self.assertFalse(result.success)
        self.assertIn('insufficient', result.error.lower())
        
    @patch('autobot.v2.order_executor.krakenex')
    def test_execute_stop_loss_order(self, mock_krakenex):
        """Test création ordre stop-loss"""
        mock_api = MagicMock()
        mock_krakenex.API.return_value = mock_api
        mock_api.query_private.return_value = {
            'result': {
                'txid': ['SL-TXID-456'],
                'descr': {'order': 'sell 0.01 XXBTZEUR @ stop loss 45000.0'}
            }
        }
        
        executor = OrderExecutor(self.api_key, self.api_secret)
        result = executor.execute_stop_loss_order(
            'XXBTZEUR', OrderSide.SELL, 0.01, 45000.0
        )
        
        self.assertTrue(result.success)
        self.assertEqual(result.txid, 'SL-TXID-456')
        
    @patch('autobot.v2.order_executor.krakenex')
    def test_cancel_order(self, mock_krakenex):
        """Test annulation ordre"""
        mock_api = MagicMock()
        mock_krakenex.API.return_value = mock_api
        mock_api.query_private.return_value = {
            'result': {'count': 1}
        }
        
        executor = OrderExecutor(self.api_key, self.api_secret)
        success = executor.cancel_order('TEST-TXID-123')
        
        self.assertTrue(success)
        
    @patch('autobot.v2.order_executor.krakenex')
    def test_get_order_status(self, mock_krakenex):
        """Test récupération statut ordre"""
        mock_api = MagicMock()
        mock_krakenex.API.return_value = mock_api
        mock_api.query_private.return_value = {
            'result': {'TEST-TXID-123': {
                'status': 'closed',
                'vol_exec': '0.01',
                'price': '50000.0',
                'avg_price': '50100.0',
                'fee': '0.52'
            }}
        }
        
        executor = OrderExecutor(self.api_key, self.api_secret)
        status = executor.get_order_status('TEST-TXID-123')
        
        self.assertIsNotNone(status)
        self.assertEqual(status.status, 'closed')
        self.assertEqual(status.volume_exec, 0.01)
        
    @patch('autobot.v2.order_executor.krakenex')
    def test_rate_limiting(self, mock_krakenex):
        """Test respect rate limiting"""
        mock_api = MagicMock()
        mock_krakenex.API.return_value = mock_api
        mock_api.query_private.return_value = {
            'result': {'txid': ['TEST-TXID']}
        }
        
        executor = OrderExecutor(self.api_key, self.api_secret)
        
        # Exécuter plusieurs ordres rapidement
        import time
        start = time.time()
        for i in range(3):
            executor._safe_api_call('AddOrder', pair='XXBTZEUR', type='buy', ordertype='market', volume='0.001')
        elapsed = time.time() - start
        
        # Vérifier qu'on a attendu au moins 2 secondes (3 appels × 1s min_interval)
        self.assertGreaterEqual(elapsed, 2.0)
        
    def test_volume_validation(self):
        """Test validation volume minimum"""
        executor = OrderExecutor(self.api_key, self.api_secret)
        
        # Volume trop faible
        result = executor.execute_market_order('XXBTZEUR', OrderSide.BUY, 0.00001)
        self.assertFalse(result.success)
        self.assertIn('minimum', result.error.lower())
        
    @patch('autobot.v2.order_executor.krakenex')
    def test_circuit_breaker(self, mock_krakenex):
        """Test circuit breaker après erreurs consécutives"""
        mock_api = MagicMock()
        mock_krakenex.API.return_value = mock_api
        mock_api.query_private.return_value = {
            'error': ['EService:Unavailable']
        }
        
        executor = OrderExecutor(self.api_key, self.api_secret)
        
        # Simuler 10 erreurs consécutives
        for i in range(10):
            executor._safe_api_call('AddOrder', pair='XXBTZEUR', type='buy')
        
        # Vérifier que le circuit breaker est déclenché
        self.assertGreaterEqual(executor._consecutive_errors, 10)
        

class TestOrderResult(unittest.TestCase):
    """Tests pour OrderResult dataclass"""
    
    def test_success_result(self):
        """Test résultat succès"""
        result = OrderResult(
            success=True,
            txid='TEST-123',
            executed_price=50000.0,
            executed_volume=0.01,
            fees=0.52
        )
        
        self.assertTrue(result.success)
        self.assertIsNone(result.error)
        self.assertEqual(result.total_cost, 500.52)  # price * volume + fees
        
    def test_failure_result(self):
        """Test résultat échec"""
        result = OrderResult(
            success=False,
            error='Insufficient funds'
        )
        
        self.assertFalse(result.success)
        self.assertEqual(result.error, 'Insufficient funds')
        

if __name__ == '__main__':
    unittest.main()
