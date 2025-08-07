"""
SuperAGI Integration Module for AUTOBOT

This module provides integration with SuperAGI for advanced AI agent orchestration
capabilities. It extends the base SuperAGIAgent with specialized functionality for
trading, e-commerce, and security operations.
"""

import os
import json
import time
import logging
import requests
from typing import Dict, Any, List, Optional, Union, Tuple
from datetime import datetime

from .orchestrator import SuperAGIAgent, AgentType, AgentStatus, AgentMessage

logger = logging.getLogger(__name__)

class SuperAGIConnector:
    """
    Connector for SuperAGI API integration.
    Handles communication with SuperAGI platform.
    """
    
    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.superagi.com/v1",
        timeout: int = 30
    ):
        """
        Initialize SuperAGI connector.
        
        Args:
            api_key: SuperAGI API key
            base_url: SuperAGI API base URL
            timeout: Request timeout in seconds
        """
        self.api_key = api_key
        self.base_url = base_url
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        })
        
        logger.info(f"SuperAGI connector initialized with base URL {base_url}")
    
    def create_agent(self, name: str, description: str, tools: List[str] = None) -> Dict[str, Any]:
        """
        Create a new agent in SuperAGI.
        
        Args:
            name: Agent name
            description: Agent description
            tools: List of tool names to enable
            
        Returns:
            Dict: Created agent details
        """
        tools = tools or []
        
        try:
            response = self.session.post(
                f"{self.base_url}/agents",
                json={
                    "name": name,
                    "description": description,
                    "tools": tools
                },
                timeout=self.timeout
            )
            
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to create SuperAGI agent: {str(e)}")
            return {"error": str(e)}
    
    def run_agent(self, agent_id: str, task: str, resources: List[str] = None) -> Dict[str, Any]:
        """
        Run an agent with a specific task.
        
        Args:
            agent_id: SuperAGI agent ID
            task: Task description
            resources: List of resource URLs
            
        Returns:
            Dict: Run details
        """
        resources = resources or []
        
        try:
            response = self.session.post(
                f"{self.base_url}/agents/{agent_id}/runs",
                json={
                    "task": task,
                    "resources": resources
                },
                timeout=self.timeout
            )
            
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to run SuperAGI agent: {str(e)}")
            return {"error": str(e)}
    
    def get_run_status(self, agent_id: str, run_id: str) -> Dict[str, Any]:
        """
        Get the status of an agent run.
        
        Args:
            agent_id: SuperAGI agent ID
            run_id: Run ID
            
        Returns:
            Dict: Run status
        """
        try:
            response = self.session.get(
                f"{self.base_url}/agents/{agent_id}/runs/{run_id}",
                timeout=self.timeout
            )
            
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to get SuperAGI run status: {str(e)}")
            return {"error": str(e)}
    
    def stop_run(self, agent_id: str, run_id: str) -> Dict[str, Any]:
        """
        Stop an agent run.
        
        Args:
            agent_id: SuperAGI agent ID
            run_id: Run ID
            
        Returns:
            Dict: Stop result
        """
        try:
            response = self.session.post(
                f"{self.base_url}/agents/{agent_id}/runs/{run_id}/stop",
                timeout=self.timeout
            )
            
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to stop SuperAGI run: {str(e)}")
            return {"error": str(e)}
    
    def get_agent_tools(self) -> List[Dict[str, Any]]:
        """
        Get available tools for agents.
        
        Returns:
            List: Available tools
        """
        try:
            response = self.session.get(
                f"{self.base_url}/tools",
                timeout=self.timeout
            )
            
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to get SuperAGI tools: {str(e)}")
            return []


class TradingSuperAGIAgent(SuperAGIAgent):
    """
    SuperAGI agent specialized for trading operations.
    """
    
    def __init__(
        self,
        agent_id: str,
        name: str,
        config: Dict[str, Any] = None,
        api_key: str = None,
        base_url: str = "https://api.superagi.com/v1"
    ):
        """
        Initialize a trading SuperAGI agent.
        
        Args:
            agent_id: Unique ID for this agent
            name: Human-readable name
            config: Agent configuration
            api_key: SuperAGI API key
            base_url: SuperAGI API base URL
        """
        super().__init__(agent_id, name, config, api_key, base_url)
        
        self.trading_strategies = config.get("trading_strategies", ["trend_following", "mean_reversion"])
        self.risk_parameters = config.get("risk_parameters", {
            "max_position_size": 1.0,
            "max_drawdown": 0.1,
            "stop_loss": 0.05
        })
        
        self.register_message_handler("analyze_market", self._handle_analyze_market)
        self.register_message_handler("generate_trading_strategy", self._handle_generate_trading_strategy)
        
        trading_tools = [
            "market_data_tool",
            "technical_analysis_tool",
            "order_execution_tool",
            "risk_management_tool"
        ]
        
        self._initialize_session(additional_tools=trading_tools)
        
        logger.info(f"TradingSuperAGIAgent {self.name} initialized with {len(self.trading_strategies)} strategies")
    
    def _handle_analyze_market(self, message: AgentMessage):
        """
        Handle a request to analyze market conditions.
        
        Args:
            message: Message containing analysis parameters
        """
        content = message.content
        symbol = content.get("symbol", "BTC/USD")
        timeframe = content.get("timeframe", "1h")
        
        autonomous_mode = self.config.get("autonomous_mode", True)
        visible_interface = self.config.get("visible_interface", False)
        
        task = f"Analyze market conditions for {symbol} on {timeframe} timeframe. " \
               f"Identify key support/resistance levels, trend direction, and potential entry/exit points."
        
        if self.superagi_agent_id and self.connector:
            run_result = self.connector.run_agent(
                agent_id=self.superagi_agent_id,
                task=task
            )
            
            run_id = run_result.get("id")
            if run_id:
                self.active_runs[run_id] = {
                    "task": "analyze_market",
                    "parameters": content,
                    "requester_id": message.sender_id,
                    "start_time": int(time.time())
                }
                
                if not autonomous_mode or visible_interface:
                    self.send_message(
                        recipient_id=message.sender_id,
                        message_type="analysis_started",
                        content={
                            "run_id": run_id,
                            "symbol": symbol,
                            "timeframe": timeframe,
                            "status": "processing"
                        }
                    )
                
                if autonomous_mode and not visible_interface:
                    logger.debug(f"TradingSuperAGIAgent {self.id} started market analysis for {symbol}")
                else:
                    logger.info(f"TradingSuperAGIAgent {self.id} started market analysis for {symbol}")
            else:
                if not autonomous_mode or visible_interface:
                    self.send_message(
                        recipient_id=message.sender_id,
                        message_type="analysis_error",
                        content={
                            "error": "Failed to start analysis",
                            "details": run_result.get("error", "Unknown error")
                        }
                    )
                
                logger.error(f"TradingSuperAGIAgent {self.id} failed to start analysis: {run_result.get('error', 'Unknown error')}")
        else:
            if not autonomous_mode or visible_interface:
                self.send_message(
                    recipient_id=message.sender_id,
                    message_type="analysis_error",
                    content={
                        "error": "SuperAGI agent not initialized"
                    }
                )
            
            logger.error(f"TradingSuperAGIAgent {self.id} failed to analyze market: SuperAGI agent not initialized")
    
    def _handle_generate_trading_strategy(self, message: AgentMessage):
        """
        Handle a request to generate a trading strategy.
        
        Args:
            message: Message containing strategy parameters
        """
        content = message.content
        strategy_type = content.get("strategy_type", "trend_following")
        symbol = content.get("symbol", "BTC/USD")
        timeframe = content.get("timeframe", "1h")
        risk_level = content.get("risk_level", "medium")
        
        autonomous_mode = self.config.get("autonomous_mode", True)
        visible_interface = self.config.get("visible_interface", False)
        
        task = f"Generate a {strategy_type} trading strategy for {symbol} on {timeframe} timeframe " \
               f"with {risk_level} risk level. Include entry/exit rules, position sizing, and risk management."
        
        if self.superagi_agent_id and self.connector:
            run_result = self.connector.run_agent(
                agent_id=self.superagi_agent_id,
                task=task
            )
            
            run_id = run_result.get("id")
            if run_id:
                self.active_runs[run_id] = {
                    "task": "generate_trading_strategy",
                    "parameters": content,
                    "requester_id": message.sender_id,
                    "start_time": int(time.time())
                }
                
                if not autonomous_mode or visible_interface:
                    self.send_message(
                        recipient_id=message.sender_id,
                        message_type="strategy_generation_started",
                        content={
                            "run_id": run_id,
                            "strategy_type": strategy_type,
                            "symbol": symbol,
                            "timeframe": timeframe,
                            "status": "processing"
                        }
                    )
                
                if autonomous_mode and not visible_interface:
                    logger.debug(f"TradingSuperAGIAgent {self.id} started strategy generation for {strategy_type}")
                else:
                    logger.info(f"TradingSuperAGIAgent {self.id} started strategy generation for {strategy_type}")
            else:
                if not autonomous_mode or visible_interface:
                    self.send_message(
                        recipient_id=message.sender_id,
                        message_type="strategy_generation_error",
                        content={
                            "error": "Failed to start strategy generation",
                            "details": run_result.get("error", "Unknown error")
                        }
                    )
                
                logger.error(f"TradingSuperAGIAgent {self.id} failed to start strategy generation: {run_result.get('error', 'Unknown error')}")
        else:
            if not autonomous_mode or visible_interface:
                self.send_message(
                    recipient_id=message.sender_id,
                    message_type="strategy_generation_error",
                    content={
                        "error": "SuperAGI agent not initialized"
                    }
                )
            
            logger.error(f"TradingSuperAGIAgent {self.id} failed to generate strategy: SuperAGI agent not initialized")


class EcommerceSuperAGIAgent(SuperAGIAgent):
    """
    SuperAGI agent specialized for e-commerce operations.
    """
    
    def __init__(
        self,
        agent_id: str,
        name: str,
        config: Dict[str, Any] = None,
        api_key: str = None,
        base_url: str = "https://api.superagi.com/v1"
    ):
        """
        Initialize an e-commerce SuperAGI agent.
        
        Args:
            agent_id: Unique ID for this agent
            name: Human-readable name
            config: Agent configuration
            api_key: SuperAGI API key
            base_url: SuperAGI API base URL
        """
        super().__init__(agent_id, name, config, api_key, base_url)
        
        self.inventory_sources = config.get("inventory_sources", ["amazon", "ebay"])
        self.pricing_strategy = config.get("pricing_strategy", "competitive")
        
        self.register_message_handler("analyze_inventory", self._handle_analyze_inventory)
        self.register_message_handler("optimize_pricing", self._handle_optimize_pricing)
        self.register_message_handler("generate_product_description", self._handle_generate_product_description)
        
        ecommerce_tools = [
            "inventory_management_tool",
            "pricing_optimization_tool",
            "product_description_tool",
            "market_research_tool"
        ]
        
        self._initialize_session(additional_tools=ecommerce_tools)
        
        logger.info(f"EcommerceSuperAGIAgent {self.name} initialized with {len(self.inventory_sources)} inventory sources")
    
    def _handle_analyze_inventory(self, message: AgentMessage):
        """
        Handle a request to analyze inventory.
        
        Args:
            message: Message containing analysis parameters
        """
        content = message.content
        source = content.get("source", "all")
        category = content.get("category", "all")
        
        autonomous_mode = self.config.get("autonomous_mode", True)
        visible_interface = self.config.get("visible_interface", False)
        
        task = f"Analyze inventory for {category} category from {source} source. " \
               f"Identify slow-moving items, potential markdowns, and restocking opportunities."
        
        if self.superagi_agent_id and self.connector:
            run_result = self.connector.run_agent(
                agent_id=self.superagi_agent_id,
                task=task
            )
            
            run_id = run_result.get("id")
            if run_id:
                self.active_runs[run_id] = {
                    "task": "analyze_inventory",
                    "parameters": content,
                    "requester_id": message.sender_id,
                    "start_time": int(time.time())
                }
                
                if not autonomous_mode or visible_interface:
                    self.send_message(
                        recipient_id=message.sender_id,
                        message_type="inventory_analysis_started",
                        content={
                            "run_id": run_id,
                            "source": source,
                            "category": category,
                            "status": "processing"
                        }
                    )
                
                if autonomous_mode and not visible_interface:
                    logger.debug(f"EcommerceSuperAGIAgent {self.id} started inventory analysis for {category}")
                else:
                    logger.info(f"EcommerceSuperAGIAgent {self.id} started inventory analysis for {category}")
            else:
                if not autonomous_mode or visible_interface:
                    self.send_message(
                        recipient_id=message.sender_id,
                        message_type="inventory_analysis_error",
                        content={
                            "error": "Failed to start analysis",
                            "details": run_result.get("error", "Unknown error")
                        }
                    )
                
                logger.error(f"EcommerceSuperAGIAgent {self.id} failed to start inventory analysis: {run_result.get('error', 'Unknown error')}")
        else:
            if not autonomous_mode or visible_interface:
                self.send_message(
                    recipient_id=message.sender_id,
                    message_type="inventory_analysis_error",
                    content={
                        "error": "SuperAGI agent not initialized"
                    }
                )
            
            logger.error(f"EcommerceSuperAGIAgent {self.id} failed to analyze inventory: SuperAGI agent not initialized")
    
    def _handle_optimize_pricing(self, message: AgentMessage):
        """
        Handle a request to optimize pricing.
        
        Args:
            message: Message containing optimization parameters
        """
        content = message.content
        products = content.get("products", [])
        strategy = content.get("strategy", self.pricing_strategy)
        
        autonomous_mode = self.config.get("autonomous_mode", True)
        visible_interface = self.config.get("visible_interface", False)
        
        if not products:
            if not autonomous_mode or visible_interface:
                self.send_message(
                    recipient_id=message.sender_id,
                    message_type="pricing_optimization_error",
                    content={
                        "error": "No products specified"
                    }
                )
            logger.error(f"EcommerceSuperAGIAgent {self.id} failed to optimize pricing: No products specified")
            return
        
        product_list = ", ".join([p.get("name", f"Product {i+1}") for i, p in enumerate(products[:5])])
        if len(products) > 5:
            product_list += f" and {len(products) - 5} more"
        
        task = f"Optimize pricing for the following products using {strategy} strategy: {product_list}. " \
               f"Consider competitor prices, demand elasticity, and inventory levels."
        
        if self.superagi_agent_id and self.connector:
            run_result = self.connector.run_agent(
                agent_id=self.superagi_agent_id,
                task=task
            )
            
            run_id = run_result.get("id")
            if run_id:
                self.active_runs[run_id] = {
                    "task": "optimize_pricing",
                    "parameters": content,
                    "requester_id": message.sender_id,
                    "start_time": int(time.time())
                }
                
                if not autonomous_mode or visible_interface:
                    self.send_message(
                        recipient_id=message.sender_id,
                        message_type="pricing_optimization_started",
                        content={
                            "run_id": run_id,
                            "product_count": len(products),
                            "strategy": strategy,
                            "status": "processing"
                        }
                    )
                
                if autonomous_mode and not visible_interface:
                    logger.debug(f"EcommerceSuperAGIAgent {self.id} started pricing optimization for {len(products)} products")
                else:
                    logger.info(f"EcommerceSuperAGIAgent {self.id} started pricing optimization for {len(products)} products")
            else:
                if not autonomous_mode or visible_interface:
                    self.send_message(
                        recipient_id=message.sender_id,
                        message_type="pricing_optimization_error",
                        content={
                            "error": "Failed to start optimization",
                            "details": run_result.get("error", "Unknown error")
                        }
                    )
                
                logger.error(f"EcommerceSuperAGIAgent {self.id} failed to start pricing optimization: {run_result.get('error', 'Unknown error')}")
        else:
            if not autonomous_mode or visible_interface:
                self.send_message(
                    recipient_id=message.sender_id,
                    message_type="pricing_optimization_error",
                    content={
                        "error": "SuperAGI agent not initialized"
                    }
                )
            
            logger.error(f"EcommerceSuperAGIAgent {self.id} failed to optimize pricing: SuperAGI agent not initialized")
    
    def _handle_generate_product_description(self, message: AgentMessage):
        """
        Handle a request to generate product descriptions.
        
        Args:
            message: Message containing generation parameters
        """
        content = message.content
        product = content.get("product", {})
        style = content.get("style", "professional")
        
        autonomous_mode = self.config.get("autonomous_mode", True)
        visible_interface = self.config.get("visible_interface", False)
        
        if not product:
            if not autonomous_mode or visible_interface:
                self.send_message(
                    recipient_id=message.sender_id,
                    message_type="description_generation_error",
                    content={
                        "error": "No product specified"
                    }
                )
            logger.error(f"EcommerceSuperAGIAgent {self.id} failed to generate product description: No product specified")
            return
        
        product_name = product.get("name", "Product")
        
        task = f"Generate a {style} product description for {product_name}. " \
               f"Highlight key features, benefits, and use cases."
        
        if self.superagi_agent_id and self.connector:
            run_result = self.connector.run_agent(
                agent_id=self.superagi_agent_id,
                task=task
            )
            
            run_id = run_result.get("id")
            if run_id:
                self.active_runs[run_id] = {
                    "task": "generate_product_description",
                    "parameters": content,
                    "requester_id": message.sender_id,
                    "start_time": int(time.time())
                }
                
                if not autonomous_mode or visible_interface:
                    self.send_message(
                        recipient_id=message.sender_id,
                        message_type="description_generation_started",
                        content={
                            "run_id": run_id,
                            "product_name": product_name,
                            "style": style,
                            "status": "processing"
                        }
                    )
                
                if autonomous_mode and not visible_interface:
                    logger.debug(f"EcommerceSuperAGIAgent {self.id} started description generation for {product_name}")
                else:
                    logger.info(f"EcommerceSuperAGIAgent {self.id} started description generation for {product_name}")
            else:
                if not autonomous_mode or visible_interface:
                    self.send_message(
                        recipient_id=message.sender_id,
                        message_type="description_generation_error",
                        content={
                            "error": "Failed to start generation",
                            "details": run_result.get("error", "Unknown error")
                        }
                    )
                
                logger.error(f"EcommerceSuperAGIAgent {self.id} failed to start description generation: {run_result.get('error', 'Unknown error')}")
        else:
            if not autonomous_mode or visible_interface:
                self.send_message(
                    recipient_id=message.sender_id,
                    message_type="description_generation_error",
                    content={
                        "error": "SuperAGI agent not initialized"
                    }
                )
            
            logger.error(f"EcommerceSuperAGIAgent {self.id} failed to generate product description: SuperAGI agent not initialized")


class SecuritySuperAGIAgent(SuperAGIAgent):
    """
    SuperAGI agent specialized for security operations.
    """
    
    def __init__(
        self,
        agent_id: str,
        name: str,
        config: Dict[str, Any] = None,
        api_key: str = None,
        base_url: str = "https://api.superagi.com/v1"
    ):
        """
        Initialize a security SuperAGI agent.
        
        Args:
            agent_id: Unique ID for this agent
            name: Human-readable name
            config: Agent configuration
            api_key: SuperAGI API key
            base_url: SuperAGI API base URL
        """
        super().__init__(agent_id, name, config, api_key, base_url)
        
        self.security_policies = config.get("security_policies", ["authentication", "authorization", "encryption"])
        self.alert_thresholds = config.get("alert_thresholds", {
            "login_attempts": 5,
            "api_rate": 100,
            "suspicious_activity": 0.7
        })
        
        self.register_message_handler("analyze_security_logs", self._handle_analyze_security_logs)
        self.register_message_handler("generate_security_policy", self._handle_generate_security_policy)
        
        security_tools = [
            "log_analysis_tool",
            "threat_detection_tool",
            "policy_generation_tool",
            "vulnerability_assessment_tool"
        ]
        
        self._initialize_session(additional_tools=security_tools)
        
        logger.info(f"SecuritySuperAGIAgent {self.name} initialized with {len(self.security_policies)} policies")
    
    def _handle_analyze_security_logs(self, message: AgentMessage):
        """
        Handle a request to analyze security logs.
        
        Args:
            message: Message containing analysis parameters
        """
        content = message.content
        log_type = content.get("log_type", "authentication")
        time_range = content.get("time_range", "24h")
        
        autonomous_mode = self.config.get("autonomous_mode", True)
        visible_interface = self.config.get("visible_interface", False)
        
        task = f"Analyze {log_type} security logs for the past {time_range}. " \
               f"Identify suspicious activities, potential threats, and security vulnerabilities."
        
        if self.superagi_agent_id and self.connector:
            run_result = self.connector.run_agent(
                agent_id=self.superagi_agent_id,
                task=task
            )
            
            run_id = run_result.get("id")
            if run_id:
                self.active_runs[run_id] = {
                    "task": "analyze_security_logs",
                    "parameters": content,
                    "requester_id": message.sender_id,
                    "start_time": int(time.time())
                }
                
                if not autonomous_mode or visible_interface:
                    self.send_message(
                        recipient_id=message.sender_id,
                        message_type="security_analysis_started",
                        content={
                            "run_id": run_id,
                            "log_type": log_type,
                            "time_range": time_range,
                            "status": "processing"
                        }
                    )
                
                if autonomous_mode and not visible_interface:
                    logger.debug(f"SecuritySuperAGIAgent {self.id} started security log analysis for {log_type}")
                else:
                    logger.info(f"SecuritySuperAGIAgent {self.id} started security log analysis for {log_type}")
            else:
                if not autonomous_mode or visible_interface:
                    self.send_message(
                        recipient_id=message.sender_id,
                        message_type="security_analysis_error",
                        content={
                            "error": "Failed to start analysis",
                            "details": run_result.get("error", "Unknown error")
                        }
                    )
                
                logger.error(f"SecuritySuperAGIAgent {self.id} failed to start security log analysis: {run_result.get('error', 'Unknown error')}")
        else:
            if not autonomous_mode or visible_interface:
                self.send_message(
                    recipient_id=message.sender_id,
                    message_type="security_analysis_error",
                    content={
                        "error": "SuperAGI agent not initialized"
                    }
                )
            
            logger.error(f"SecuritySuperAGIAgent {self.id} failed to analyze security logs: SuperAGI agent not initialized")
    
    def _handle_generate_security_policy(self, message: AgentMessage):
        """
        Handle a request to generate a security policy.
        
        Args:
            message: Message containing policy parameters
        """
        content = message.content
        policy_type = content.get("policy_type", "authentication")
        compliance_framework = content.get("compliance_framework", "GDPR")
        
        autonomous_mode = self.config.get("autonomous_mode", True)
        visible_interface = self.config.get("visible_interface", False)
        
        task = f"Generate a {policy_type} security policy compliant with {compliance_framework}. " \
               f"Include implementation guidelines, monitoring procedures, and incident response protocols."
        
        if self.superagi_agent_id and self.connector:
            run_result = self.connector.run_agent(
                agent_id=self.superagi_agent_id,
                task=task
            )
            
            run_id = run_result.get("id")
            if run_id:
                self.active_runs[run_id] = {
                    "task": "generate_security_policy",
                    "parameters": content,
                    "requester_id": message.sender_id,
                    "start_time": int(time.time())
                }
                
                if not autonomous_mode or visible_interface:
                    self.send_message(
                        recipient_id=message.sender_id,
                        message_type="policy_generation_started",
                        content={
                            "run_id": run_id,
                            "policy_type": policy_type,
                            "compliance_framework": compliance_framework,
                            "status": "processing"
                        }
                    )
                
                if autonomous_mode and not visible_interface:
                    logger.debug(f"SecuritySuperAGIAgent {self.id} started policy generation for {policy_type}")
                else:
                    logger.info(f"SecuritySuperAGIAgent {self.id} started policy generation for {policy_type}")
            else:
                if not autonomous_mode or visible_interface:
                    self.send_message(
                        recipient_id=message.sender_id,
                        message_type="policy_generation_error",
                        content={
                            "error": "Failed to start generation",
                            "details": run_result.get("error", "Unknown error")
                        }
                    )
                
                logger.error(f"SecuritySuperAGIAgent {self.id} failed to start policy generation: {run_result.get('error', 'Unknown error')}")
        else:
            if not autonomous_mode or visible_interface:
                self.send_message(
                    recipient_id=message.sender_id,
                    message_type="policy_generation_error",
                    content={
                        "error": "SuperAGI agent not initialized"
                    }
                )
            
            logger.error(f"SecuritySuperAGIAgent {self.id} failed to generate security policy: SuperAGI agent not initialized")


def create_superagi_agent(
    agent_type: str,
    name: str,
    config: Dict[str, Any] = None,
    api_key: str = None,
    base_url: str = "https://api.superagi.com/v1",
    autonomous_mode: bool = True,
    visible_interface: bool = False
) -> Optional[SuperAGIAgent]:
    """
    Factory function to create a specialized SuperAGI agent.
    
    Args:
        agent_type: Type of agent to create ("trading", "ecommerce", "security")
        name: Human-readable name for the agent
        config: Agent configuration
        api_key: SuperAGI API key
        base_url: SuperAGI API base URL
        autonomous_mode: Whether to operate in autonomous mode without user intervention
        visible_interface: Whether to show the interface or operate invisibly in the background
        
    Returns:
        SuperAGIAgent: Created agent, or None if creation failed
    """
    agent_id = f"superagi_{agent_type}_{int(time.time())}"
    config = config or {}
    
    config["autonomous_mode"] = autonomous_mode
    config["visible_interface"] = visible_interface
    
    if agent_type == "trading":
        return TradingSuperAGIAgent(agent_id, name, config, api_key, base_url)
    elif agent_type == "ecommerce":
        return EcommerceSuperAGIAgent(agent_id, name, config, api_key, base_url)
    elif agent_type == "security":
        return SecuritySuperAGIAgent(agent_id, name, config, api_key, base_url)
    else:
        return SuperAGIAgent(agent_id, name, config, api_key, base_url)
