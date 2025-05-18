"""
AutobotMaster - Super Agent Orchestrateur pour AUTOBOT

Ce module définit l'agent principal qui orchestre tous les composants d'AUTOBOT
via une interface conversationnelle.
"""

import os
import logging
import yaml
from typing import Dict, List, Any, Optional, Union

from .superagi_integration import SuperAGIAgent
from .superagi_integration import TradingSuperAGIAgent, EcommerceSuperAGIAgent, SecuritySuperAGIAgent
from .superagi_integration_enhanced import EnhancedSuperAGIOrchestrator
from ..trading.ghosting_manager import GhostingManager, create_ghosting_manager
from ..autobot_security.license_manager import get_license_manager

logger = logging.getLogger(__name__)

class AutobotMasterAgent(SuperAGIAgent):
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
        base_url: str = "https://api.superagi.com",
        sub_agents: Optional[List[SuperAGIAgent]] = None
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
        self.orchestrator = None
        self.ghosting_manager = None
        self.tools = {}
        
        self._initialize_tools()
        self._initialize_orchestrator()
    
    def _initialize_tools(self):
        """Initialise les outils disponibles pour l'agent."""
        self.tools = {
            "predict": self._tool_predict,
            "backtest": self._tool_backtest,
            "train": self._tool_train,
            "ghosting": self._tool_ghosting
        }
    
    def _initialize_orchestrator(self):
        """Initialise l'orchestrateur pour gérer les sous-agents."""
        try:
            license_manager = get_license_manager()
            self.ghosting_manager = create_ghosting_manager(license_manager)
            
            self.orchestrator = EnhancedSuperAGIOrchestrator(
                api_key=self.api_key,
                base_url=self.base_url,
                config_path=None,  # Utiliser None car on passe la config directement
                autonomous_mode=True,
                visible_interface=False,
                agent_types=["trading", "ecommerce", "security"]
            )
            
            logger.info(f"AutobotMaster initialized with {len(self.sub_agents)} sub-agents")
        except Exception as e:
            logger.error(f"Error initializing orchestrator: {str(e)}")
    
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
            try:
                result = self.tools[action](**params)
                return self._format_response(action, result)
            except Exception as e:
                logger.error(f"Error executing {action}: {str(e)}")
                return f"Une erreur est survenue lors de l'exécution de {action}: {str(e)}"
        else:
            return super().process_message(message)
    
    def _interpret_message(self, message: str) -> tuple:
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
            if "stratégie" in message:
                strategy = message.split("stratégie")[1].split()[0]
            return "backtest", {"strategy": strategy}
        elif "train" in message or "entraîn" in message:
            return "train", {}
        elif "ghost" in message or "clone" in message:
            count = 1
            import re
            count_match = re.search(r'(\d+) clone', message)
            if count_match:
                count = int(count_match.group(1))
            return "ghosting", {"count": count}
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
            import requests
            response = requests.get("http://localhost:8000/predict")
            return response.json()
        except Exception as e:
            logger.error(f"Error executing prediction: {str(e)}")
            return {"prediction": "N/A", "error": str(e)}
    
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
            import requests
            response = requests.post("http://localhost:8000/backtest", json={
                "strategy": strategy,
                "symbol": symbol,
                "timeframe": timeframe
            })
            return response.json()
        except Exception as e:
            logger.error(f"Error executing backtest: {str(e)}")
            return {"strategy": strategy, "metrics": {"profit": 0, "drawdown": 0, "sharpe": 0}, "error": str(e)}
    
    def _tool_train(self) -> Dict[str, Any]:
        """
        Outil pour entraîner des modèles.
        
        Returns:
            Dict: Résultat de l'entraînement
        """
        try:
            import requests
            response = requests.post("http://localhost:8000/train")
            return response.json()
        except Exception as e:
            logger.error(f"Error executing training: {str(e)}")
            return {"job_id": "N/A", "status": "error", "error": str(e)}
    
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
            if not self.ghosting_manager:
                return {"error": "Ghosting manager not initialized"}
            
            if not markets:
                markets = ["BTC/USD", "ETH/USD"]
            
            if not strategies:
                strategies = ["momentum", "mean_reversion"]
            
            instance_ids = []
            for _ in range(count):
                config = {
                    "interval": 1,
                    "order_frequency": 0.15,
                    "fill_rate": 0.85,
                    "mean_profit": 0.015
                }
                
                instance_id = self.ghosting_manager.create_instance(
                    markets=markets,
                    strategies=strategies,
                    config=config
                )
                
                if instance_id:
                    instance_ids.append(instance_id)
            
            return {
                "success": True,
                "count": len(instance_ids),
                "instance_ids": instance_ids
            }
        except Exception as e:
            logger.error(f"Error starting ghosting instances: {str(e)}")
            return {"error": str(e)}

def create_autobot_master_agent(
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    config_path: Optional[str] = None
) -> AutobotMasterAgent:
    """
    Crée une instance de l'agent AutobotMaster.
    
    Args:
        api_key: Clé API SuperAGI (optionnelle)
        base_url: URL de base de l'API SuperAGI (optionnelle)
        config_path: Chemin vers le fichier de configuration (optionnel)
        
    Returns:
        AutobotMasterAgent: Instance de l'agent
    """
    if not config_path:
        config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 
                                   "config", "superagi_config.yaml")
    
    config = {}
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)
        except Exception as e:
            logger.error(f"Error loading config from {config_path}: {str(e)}")
    
    trading_agent = TradingSuperAGIAgent("trading-1", "Trading Agent", config.get("agents", {}).get("trading", {}), api_key, base_url)
    ecommerce_agent = EcommerceSuperAGIAgent("ecommerce-1", "E-commerce Agent", config.get("agents", {}).get("ecommerce", {}), api_key, base_url)
    security_agent = SecuritySuperAGIAgent("security-1", "Security Agent", config.get("agents", {}).get("security", {}), api_key, base_url)
    
    sub_agents = [trading_agent, ecommerce_agent, security_agent]
    
    master_config = config.get("agents", {}).get("autobot_master", {})
    return AutobotMasterAgent("master-1", "AutobotMaster", master_config, api_key, base_url, sub_agents)
