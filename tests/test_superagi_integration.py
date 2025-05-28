"""
Test script for SuperAGI integration with AUTOBOT.
"""

import os
import sys
import unittest
import requests
import asyncio
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.autobot.agents.autobot_master import AutobotMasterAgent, create_autobot_master_agent

class TestSuperAGIIntegration(unittest.TestCase):
    """Test cases for SuperAGI integration."""
    
    @classmethod
    def setUpClass(cls):
        """Set up test environment once for all tests."""
        global requests
        import requests
        
        cls._original_get = requests.get
        cls._original_post = requests.post

    def setUp(self):
        """Set up test environment."""
        self.config = {
            "agents": {
                "autobot_master": {
                    "name": "AutobotMaster",
                    "description": "Agent orchestrateur principal pour AUTOBOT"
                }
            }
        }
        
        self.patcher1 = patch("src.autobot.agents.autobot_master.get_license_manager")
        self.patcher2 = patch("src.autobot.agents.autobot_master.create_ghosting_manager")
        
        self._mock_response = MagicMock()
        self._mock_response.json.return_value = {
            "prediction": 0.75, 
            "metrics": {"profit": 0.5, "drawdown": 0.2, "sharpe": 1.5}, 
            "job_id": "123"
        }
        
        def mock_get(url, *args, **kwargs):
            return self._mock_response
            
        def mock_post(url, *args, **kwargs):
            return self._mock_response
        
        requests.get = mock_get
        requests.post = mock_post
        
        self.mock_license_manager = self.patcher1.start()
        self.mock_ghosting_manager = self.patcher2.start()
        
        self.mock_license_manager.return_value = MagicMock()
        self.mock_ghosting_manager.return_value = MagicMock()
        
        # Initialiser l'agent avec api_base au lieu de base_url
        self.agent = AutobotMasterAgent(
            agent_id="test-1",
            name="Test Agent",
            config=self.config.get("agents", {}).get("autobot_master", {}),
            api_key="test_key",
            api_base="https://api.superagi.com/v1",
            sub_agents=[]
        )
    
    def tearDown(self):
        """Clean up after tests."""
        self.patcher1.stop()
        self.patcher2.stop()
        
        requests.get = self.__class__._original_get
        requests.post = self.__class__._original_post
    
    def test_process_message_predict(self):
        """Test processing a prediction message."""
        response = self.agent.process_message("Prédis le prix de BTC")
        
        self.assertIn("Prédiction effectuée", response)
        self.assertIn("0.75", response)
    
    def test_process_message_backtest(self):
        """Test processing a backtest message."""
        response = self.agent.process_message("Exécute un backtest sur la stratégie momentum")
        
        self.assertIn("Backtest terminé", response)
        self.assertIn("Profit: 0.5", response)
    
    def test_process_message_train(self):
        """Test processing a training message."""
        response = self.agent.process_message("Lance l'entraînement du modèle")
        
        self.assertIn("Entraînement démarré", response)
        self.assertIn("123", response)
    
    def test_process_message_ghosting(self):
        """Test processing a ghosting message."""
        response = self.agent.process_message("Démarre 5 clones HFT")
        
        self.assertIn("Ghosting activé", response)
        self.assertIn("5 instances", response)

class TestWebSocketAuthentication(unittest.TestCase):
    """Test cases for WebSocket authentication."""
    
    def test_websocket_authentication(self):
        """Test WebSocket authentication function."""
        from fastapi import WebSocket
        from src.autobot.autobot_security.auth.jwt_handler import create_access_token
        from src.autobot.autobot_security.auth.user_manager import get_current_user_ws
        
        class MockWebSocket:
            def __init__(self):
                self.query_params = {"token": create_access_token({"sub": "test_user", "username": "test", "role": "user"})}
                self.cookies = {}
                
            async def close(self, code=1000):
                pass
        
        async def test_auth():
            user = await get_current_user_ws(MockWebSocket())
            return user
            
        user = asyncio.run(test_auth())
        self.assertEqual(user.id, "test_user")

if __name__ == "__main__":
    unittest.main()
