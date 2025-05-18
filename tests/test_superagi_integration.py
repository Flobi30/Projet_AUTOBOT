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
        
        with patch("src.autobot.agents.autobot_master.get_license_manager") as mock_license_manager, \
             patch("src.autobot.agents.autobot_master.create_ghosting_manager") as mock_ghosting_manager, \
             patch("requests.get") as mock_get, \
             patch("requests.post") as mock_post:
            
            mock_response = MagicMock()
            mock_response.json.return_value = {"prediction": 0.75, "metrics": {"profit": 0.5, "drawdown": 0.2, "sharpe": 1.5}, "job_id": "123"}
            mock_get.return_value = mock_response
            mock_post.return_value = mock_response
            
            mock_license_manager.return_value = MagicMock()
            mock_ghosting_manager.return_value = MagicMock()
            
            self.agent = AutobotMasterAgent(
                agent_id="test-1",
                name="Test Agent",
                config=self.config.get("agents", {}).get("autobot_master", {}),
                api_key="test_key",
                base_url="https://api.superagi.com",
                sub_agents=[]
            )
    
    def test_process_message_predict(self):
        """Test processing a prediction message."""
        with patch.object(self.agent, "_tool_predict") as mock_predict:
            mock_predict.return_value = {"prediction": 0.75}
            
            response = self.agent.process_message("Prédis le prix de BTC")
            
            mock_predict.assert_called_once()
            self.assertIn("Prédiction effectuée", response)
            self.assertIn("0.75", response)
    
    def test_process_message_backtest(self):
        """Test processing a backtest message."""
        with patch.object(self.agent, "_tool_backtest") as mock_backtest:
            mock_backtest.return_value = {
                "strategy": "momentum",
                "metrics": {"profit": 0.5, "drawdown": 0.2, "sharpe": 1.5}
            }
            
            response = self.agent.process_message("Exécute un backtest sur la stratégie momentum")
            
            mock_backtest.assert_called_once()
            self.assertIn("Backtest terminé", response)
            self.assertIn("Profit: 0.5", response)
    
    def test_process_message_train(self):
        """Test processing a training message."""
        with patch.object(self.agent, "_tool_train") as mock_train:
            mock_train.return_value = {"job_id": "123", "status": "training_started"}
            
            response = self.agent.process_message("Lance l'entraînement du modèle")
            
            mock_train.assert_called_once()
            self.assertIn("Entraînement démarré", response)
            self.assertIn("123", response)
    
    def test_process_message_ghosting(self):
        """Test processing a ghosting message."""
        with patch.object(self.agent, "_tool_ghosting") as mock_ghosting:
            mock_ghosting.return_value = {
                "success": True,
                "count": 5,
                "instance_ids": ["1", "2", "3", "4", "5"]
            }
            
            response = self.agent.process_message("Démarre 5 clones HFT")
            
            mock_ghosting.assert_called_once()
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
