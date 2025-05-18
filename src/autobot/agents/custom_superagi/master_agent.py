"""
Custom AutobotMaster Agent Implementation

This module provides a custom implementation of the AutobotMaster agent
without requiring the superagi package, avoiding dependency conflicts.
"""

import os
import logging
import re
import time
import json
from typing import Dict, List, Any, Optional, Union, Tuple

from .agent import CustomSuperAGIAgent
from .tools import create_tool

logger = logging.getLogger(__name__)

class AutobotMasterAgent(CustomSuperAGIAgent):
    """
    Agent principal qui orchestre tous les composants d'AUTOBOT.
    Fonctionne comme un super-agent qui délègue aux agents spécialisés.
    """
    
    def __init__(
        self,
        agent_id: str,
        name: str,
        config: Dict[str, Any],
        api_key: str = None,
        base_url: str = "https://api.superagi.com/v1",
        sub_agents: Optional[List[CustomSuperAGIAgent]] = None
    ):
        """
        Initialise l'agent AutobotMaster.
        
        Args:
            agent_id: Identifiant unique de l'agent
            name: Nom de l'agent
            config: Configuration de l'agent
            api_key: Clé API SuperAGI
            base_url: URL de base de l'API SuperAGI
            sub_agents: Liste des agents subordonnés
        """
        super().__init__(agent_id, name, config, api_key, base_url)
        
        self.sub_agents = sub_agents or []
        self.tools = {}
        self.tool_instances = {}
        
        self._initialize_tools()
    
    def _initialize_tools(self):
        """Initialise les outils disponibles pour l'agent."""
        self.tools = {
            "predict": self._tool_predict,
            "backtest": self._tool_backtest,
            "train": self._tool_train,
            "ghosting": self._tool_ghosting
        }
        
        for tool_name in self.tools.keys():
            self.tool_instances[tool_name] = create_tool(tool_name)
    
    def process_message(self, message: str) -> str:
        """
        Traite un message entrant et génère une réponse.
        
        Args:
            message: Message à traiter
            
        Returns:
            str: Réponse générée
        """
        if not message:
            return "Bonjour, je suis AutobotMaster. Comment puis-je vous aider?"
        
        action, params = self._interpret_message(message)
        
        if action in self.tools:
            result = self.tools[action](**params)
            return self._format_response(action, result)
        else:
            return "Je ne suis pas sûr de comprendre votre demande. Pouvez-vous reformuler ou utiliser une commande comme 'prédire', 'backtest', 'entraîner' ou 'démarrer des clones'?"
    
    def _interpret_message(self, message: str) -> Tuple[str, Dict[str, Any]]:
        """
        Interprète un message pour déterminer l'action à effectuer.
        
        Args:
            message: Message à interpréter
            
        Returns:
            tuple: (action, paramètres)
        """
        message = message.lower()
        
        if "préd" in message or "predict" in message:
            return "predict", {}
        elif "backtest" in message or "test" in message:
            strategy = "default"
            symbol = "BTC/USD"
            timeframe = "1h"
            
            strategy_match = re.search(r'stratégie\s+(\w+)', message)
            if strategy_match:
                strategy = strategy_match.group(1)
            
            symbol_match = re.search(r'(btc|eth|ltc|xrp|bnb)(/|\s+)(usd|usdt|eur)', message, re.IGNORECASE)
            if symbol_match:
                symbol = f"{symbol_match.group(1).upper()}/{symbol_match.group(3).upper()}"
            
            timeframe_match = re.search(r'(\d+)([mhd])', message)
            if timeframe_match:
                timeframe = f"{timeframe_match.group(1)}{timeframe_match.group(2)}"
            
            return "backtest", {
                "strategy": strategy,
                "symbol": symbol,
                "timeframe": timeframe
            }
        elif "train" in message or "entraîn" in message:
            return "train", {}
        elif "ghost" in message or "clone" in message:
            count = 1
            markets = ["BTC/USD"]
            strategies = ["default"]
            
            count_match = re.search(r'(\d+)\s+(clone|instance)', message)
            if count_match:
                count = int(count_match.group(1))
            
            markets_match = re.findall(r'(btc|eth|ltc|xrp|bnb)(/|\s+)(usd|usdt|eur)', message, re.IGNORECASE)
            if markets_match:
                markets = [f"{m[0].upper()}/{m[2].upper()}" for m in markets_match]
            
            strategies_match = re.findall(r'stratégie\s+(\w+)', message)
            if strategies_match:
                strategies = strategies_match
            
            return "ghosting", {
                "count": count,
                "markets": markets,
                "strategies": strategies
            }
        else:
            return "unknown", {}
    
    def _format_response(self, action: str, result: Any) -> str:
        """
        Formate une réponse en fonction de l'action et du résultat.
        
        Args:
            action: Action effectuée
            result: Résultat de l'action
            
        Returns:
            str: Réponse formatée
        """
        if action == "predict":
            return f"Prédiction effectuée. Résultat : {result.get('prediction', 'N/A')}"
        elif action == "backtest":
            metrics = result.get('metrics', {})
            return f"Backtest terminé. Profit: {metrics.get('profit', 0)}, Drawdown: {metrics.get('drawdown', 0)}, Sharpe: {metrics.get('sharpe', 0)}"
        elif action == "train":
            return f"Entraînement démarré. Job ID: {result.get('job_id', 'N/A')}"
        elif action == "ghosting":
            return f"Ghosting activé. {result.get('count', 0)} instances démarrées."
        else:
            return str(result)
    
    def _tool_predict(self) -> Dict[str, Any]:
        """
        Outil pour exécuter des prédictions de trading.
        
        Returns:
            Dict: Résultat de la prédiction
        """
        try:
            return self.tool_instances["predict"].execute()
        except Exception as e:
            logger.error(f"Error executing prediction: {str(e)}")
            return {"error": str(e)}
    
    def _tool_backtest(self, strategy: str = "default", symbol: str = "BTC/USD", timeframe: str = "1h") -> Dict[str, Any]:
        """
        Outil pour exécuter des backtests.
        
        Args:
            strategy: Stratégie à tester
            symbol: Symbole à tester
            timeframe: Timeframe à utiliser
            
        Returns:
            Dict: Résultat du backtest
        """
        try:
            return self.tool_instances["backtest"].execute(
                strategy=strategy,
                symbol=symbol,
                timeframe=timeframe
            )
        except Exception as e:
            logger.error(f"Error executing backtest: {str(e)}")
            return {"error": str(e)}
    
    def _tool_train(self) -> Dict[str, Any]:
        """
        Outil pour entraîner des modèles.
        
        Returns:
            Dict: Résultat de l'entraînement
        """
        try:
            return self.tool_instances["train"].execute()
        except Exception as e:
            logger.error(f"Error executing training: {str(e)}")
            return {"error": str(e)}
    
    def _tool_ghosting(self, count: int = 1, markets: List[str] = None, strategies: List[str] = None) -> Dict[str, Any]:
        """
        Outil pour démarrer des instances ghosting.
        
        Args:
            count: Nombre d'instances à démarrer
            markets: Liste des marchés
            strategies: Liste des stratégies
            
        Returns:
            Dict: Résultat de l'opération
        """
        try:
            return self.tool_instances["ghosting"].execute(
                count=count,
                markets=markets,
                strategies=strategies
            )
        except Exception as e:
            logger.error(f"Error executing ghosting: {str(e)}")
            return {"error": str(e)}

def create_autobot_master_agent(
    config_path: Optional[str] = None,
    api_key: Optional[str] = None,
    base_url: str = "https://api.superagi.com/v1"
) -> Optional[AutobotMasterAgent]:
    """
    Crée un agent AutobotMaster.
    
    Args:
        config_path: Chemin vers le fichier de configuration
        api_key: Clé API SuperAGI
        base_url: URL de base de l'API SuperAGI
        
    Returns:
        AutobotMasterAgent: Agent créé, ou None si la création a échoué
    """
    try:
        config = {}
        if config_path and os.path.exists(config_path):
            try:
                with open(config_path, 'r') as f:
                    try:
                        config = json.load(f) or {}
                    except json.JSONDecodeError:
                        for line in f:
                            line = line.strip()
                            if line and not line.startswith('#'):
                                try:
                                    key, value = line.split('=', 1)
                                    config[key.strip()] = value.strip()
                                except ValueError:
                                    pass
            except Exception as e:
                logger.warning(f"Failed to load config from {config_path}: {str(e)}")
        
        if not api_key and "api_key" in config:
            api_key = config["api_key"]
        
        if "base_url" in config:
            base_url = config["base_url"]
        
        agent_id = f"autobot_master_{int(time.time())}"
        agent = AutobotMasterAgent(
            agent_id=agent_id,
            name="AutobotMaster",
            config=config.get("agents", {}).get("autobot_master", {}),
            api_key=api_key,
            base_url=base_url
        )
        
        logger.info(f"Created AutobotMaster agent {agent_id}")
        return agent
    except Exception as e:
        logger.error(f"Failed to create AutobotMaster agent: {str(e)}")
        return None
