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
        
        import src.autobot.agents.autobot_master
        
        self.patcher1 = patch("src.autobot.agents.autobot_master.get_license_manager")
        self.patcher2 = patch("src.autobot.agents.autobot_master.create_ghosting_manager")
        self.patcher3 = patch("src.autobot.agents.autobot_master.requests.get")
        self.patcher4 = patch("src.autobot.agents.autobot_master.requests.post")
        
        self.mock_license_manager = self.patcher1.start()
        self.mock_ghosting_manager = self.patcher2.start()
        self.mock_get = self.patcher3.start()
        self.mock_post = self.patcher4.start()
        
        mock_response = MagicMock()
        mock_response.json.return_value = {"prediction": 0.75, "metrics": {"profit": 0.5, "drawdown": 0.2, "sharpe": 1.5}, "job_id": "123"}
        self.mock_get.return_value = mock_response
        self.mock_post.return_value = mock_response
        
        self.mock_license_manager.return_value = MagicMock()
        self.mock_ghosting_manager.return_value = MagicMock()
        
        self.agent = AutobotMasterAgent(
            agent_id="test-1",
            name="Test Agent",
            config=self.config.get("agents", {}).get("autobot_master", {}),
            api_key="test_key",
            api_base="https://api.superagi.com/v1",  # Utilisez api_base au lieu de base_url
            sub_agents=[]
        )
    
    def tearDown(self):
        """Clean up after tests."""
        self.patcher1.stop()
        self.patcher2.stop()
        self.patcher3.stop()
        self.patcher4.stop()
    
    def test_process_message_predict(self):
        """Test processing a prediction message."""
        response = self.agent.process_message("Prédis le prix de BTC")
        
        self.mock_get.assert_called_once_with("http://localhost:8000/predict")
        
        self.assertIn("Prédiction effectuée", response)
        self.assertIn("0.75", response)
    
    def test_process_message_backtest(self):
        """Test processing a backtest message."""
        response = self.agent.process_message("Exécute un backtest sur la stratégie momentum")
        
        self.mock_post.assert_called_once()
        args, kwargs = self.mock_post.call_args
        self.assertEqual(args[0], "http://localhost:8000/backtest")
        self.assertIn("json", kwargs)
        self.assertEqual(kwargs["json"]["strategy"], "momentum")
        
        self.assertIn("Backtest terminé", response)
        self.assertIn("Profit: 0.5", response)
    
    def test_process_message_train(self):
        """Test processing a training message."""
        response = self.agent.process_message("Lance l'entraînement du modèle")
        
        self.mock_post.assert_called_once_with("http://localhost:8000/train")
        
        self.assertIn("Entraînement démarré", response)
        self.assertIn("123", response)
    
    def test_process_message_ghosting(self):
        """Test processing a ghosting message."""
        response = self.agent.process_message("Démarre 5 clones HFT")
        
        self.mock_post.assert_called_once_with("http://localhost:8000/ghosting/start")
        
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
