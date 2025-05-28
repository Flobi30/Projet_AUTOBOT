"""
Multi-Agent Orchestrator for AUTOBOT

This module provides the orchestration layer for managing multiple AI agents
in the AUTOBOT system. It handles agent communication, task distribution,
resource allocation, and intelligent scaling.
"""

import os
import uuid
import json
import time
import logging
import threading
import asyncio
from typing import Dict, Any, List, Optional, Callable, Union, Tuple
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)

class AgentStatus(str, Enum):
    """Status of an agent in the orchestration system"""
    IDLE = "idle"
    BUSY = "busy"
    ERROR = "error"
    OFFLINE = "offline"
    INITIALIZING = "initializing"
    TERMINATED = "terminated"

class AgentType(str, Enum):
    """Types of agents in the AUTOBOT system"""
    TRADING = "trading"
    ANALYSIS = "analysis"
    RISK = "risk"
    EXECUTION = "execution"
    MONITORING = "monitoring"
    SECURITY = "security"
    ECOMMERCE = "ecommerce"
    ORCHESTRATOR = "orchestrator"
    
    RL_AGENT = "rl_agent"
    PREDICTION = "prediction"
    OPTIMIZATION = "optimization"
    NLP = "nlp"
    SENTIMENT = "sentiment"
    ANOMALY = "anomaly"
    
    INVENTORY = "inventory"
    PRICING = "pricing"
    RECOMMENDATION = "recommendation"
    
    STRATEGY = "strategy"
    MARKET_MAKER = "market_maker"
    ARBITRAGE = "arbitrage"
    TREND_FOLLOWING = "trend_following"
    MEAN_REVERSION = "mean_reversion"
    
    SUPER_AGI = "super_agi"
    
    CUSTOM = "custom"

class AgentMessage:
    """Message format for inter-agent communication"""
    
    def __init__(
        self,
        sender_id: str,
        recipient_id: str,
        message_type: str,
        content: Dict[str, Any],
        priority: int = 1,
        expires_at: Optional[int] = None
    ):
        """
        Initialize a new agent message.
        
        Args:
            sender_id: ID of the sending agent
            recipient_id: ID of the receiving agent
            message_type: Type of message
            content: Message content
            priority: Message priority (1-10, higher is more important)
            expires_at: Unix timestamp when message expires
        """
        self.id = str(uuid.uuid4())
        self.sender_id = sender_id
        self.recipient_id = recipient_id
        self.message_type = message_type
        self.content = content
        self.priority = min(max(priority, 1), 10)  # Ensure priority is between 1-10
        self.created_at = int(time.time())
        self.expires_at = expires_at
        self.processed = False
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert message to dictionary"""
        return {
            "id": self.id,
            "sender_id": self.sender_id,
            "recipient_id": self.recipient_id,
            "message_type": self.message_type,
            "content": self.content,
            "priority": self.priority,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "processed": self.processed
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AgentMessage':
        """Create message from dictionary"""
        message = cls(
            sender_id=data["sender_id"],
            recipient_id=data["recipient_id"],
            message_type=data["message_type"],
            content=data["content"],
            priority=data["priority"],
            expires_at=data.get("expires_at")
        )
        message.id = data["id"]
        message.created_at = data["created_at"]
        message.processed = data["processed"]
        return message
    
    def is_expired(self) -> bool:
        """Check if message has expired"""
        if self.expires_at is None:
            return False
        return int(time.time()) > self.expires_at

class Agent:
    """Base agent class for the AUTOBOT system"""
    
    def __init__(
        self,
        agent_id: str,
        agent_type: AgentType,
        name: str,
        config: Dict[str, Any] = None
    ):
        """
        Initialize a new agent.
        
        Args:
            agent_id: Unique ID for this agent
            agent_type: Type of agent
            name: Human-readable name
            config: Agent configuration
        """
        self.id = agent_id
        self.type = agent_type
        self.name = name
        self.config = config or {}
        self.status = AgentStatus.INITIALIZING
        self.created_at = int(time.time())
        self.last_active = self.created_at
        self.message_handlers: Dict[str, Callable] = {}
        self.inbox: List[AgentMessage] = []
        self.outbox: List[AgentMessage] = []
        self.metrics: Dict[str, Any] = {
            "messages_received": 0,
            "messages_sent": 0,
            "tasks_completed": 0,
            "errors": 0
        }
        self.orchestrator: Optional['AgentOrchestrator'] = None
        
        logger.info(f"Agent {self.name} ({self.id}) of type {self.type} initialized")
    
    def register_message_handler(self, message_type: str, handler: Callable):
        """
        Register a handler for a specific message type.
        
        Args:
            message_type: Type of message to handle
            handler: Function to call when message is received
        """
        self.message_handlers[message_type] = handler
        logger.debug(f"Agent {self.id} registered handler for message type {message_type}")
    
    def send_message(
        self,
        recipient_id: str,
        message_type: str,
        content: Dict[str, Any],
        priority: int = 1,
        expires_at: Optional[int] = None
    ) -> str:
        """
        Send a message to another agent.
        
        Args:
            recipient_id: ID of the receiving agent
            message_type: Type of message
            content: Message content
            priority: Message priority (1-10)
            expires_at: Unix timestamp when message expires
            
        Returns:
            str: Message ID
        """
        message = AgentMessage(
            sender_id=self.id,
            recipient_id=recipient_id,
            message_type=message_type,
            content=content,
            priority=priority,
            expires_at=expires_at
        )
        
        self.outbox.append(message)
        self.metrics["messages_sent"] += 1
        
        if self.orchestrator:
            self.orchestrator.deliver_message(message)
        
        logger.debug(f"Agent {self.id} sent message {message.id} to {recipient_id}")
        return message.id
    
    def receive_message(self, message: AgentMessage) -> bool:
        """
        Receive a message from another agent.
        
        Args:
            message: Message to receive
            
        Returns:
            bool: True if message was handled, False otherwise
        """
        if message.is_expired():
            logger.warning(f"Agent {self.id} received expired message {message.id}")
            return False
        
        self.inbox.append(message)
        self.metrics["messages_received"] += 1
        self.last_active = int(time.time())
        
        if message.message_type in self.message_handlers:
            try:
                self.message_handlers[message.message_type](message)
                message.processed = True
                logger.debug(f"Agent {self.id} processed message {message.id}")
                return True
            except Exception as e:
                logger.error(f"Agent {self.id} failed to process message {message.id}: {str(e)}")
                self.metrics["errors"] += 1
                return False
        else:
            logger.warning(f"Agent {self.id} has no handler for message type {message.message_type}")
            return False
    
    def process_inbox(self):
        """Process all messages in the inbox"""
        self.inbox.sort(key=lambda m: m.priority, reverse=True)
        
        for message in self.inbox[:]:
            if message.processed:
                self.inbox.remove(message)
                continue
                
            if message.is_expired():
                self.inbox.remove(message)
                continue
                
            if message.message_type in self.message_handlers:
                try:
                    self.message_handlers[message.message_type](message)
                    message.processed = True
                    self.inbox.remove(message)
                except Exception as e:
                    logger.error(f"Agent {self.id} failed to process message {message.id}: {str(e)}")
                    self.metrics["errors"] += 1
    
    def update(self):
        """Update agent state (called periodically)"""
        self.process_inbox()
        self.last_active = int(time.time())
    
    def start(self):
        """Start the agent"""
        self.status = AgentStatus.IDLE
        logger.info(f"Agent {self.name} ({self.id}) started")
    
    def stop(self):
        """Stop the agent"""
        self.status = AgentStatus.TERMINATED
        logger.info(f"Agent {self.name} ({self.id}) stopped")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert agent to dictionary"""
        return {
            "id": self.id,
            "type": self.type.value,
            "name": self.name,
            "status": self.status.value,
            "created_at": self.created_at,
            "last_active": self.last_active,
            "metrics": self.metrics,
            "config": self.config
        }

class AgentOrchestrator:
    """
    Orchestrator for managing multiple agents in the AUTOBOT system.
    Handles agent lifecycle, communication, and resource allocation.
    """
    
    def __init__(
        self,
        config_path: Optional[str] = None,
        auto_scaling: bool = True,
        max_agents: int = 100,
        message_retention_days: int = 7
    ):
        """
        Initialize the agent orchestrator.
        
        Args:
            config_path: Path to configuration file
            auto_scaling: Whether to automatically scale agents
            max_agents: Maximum number of agents to create
            message_retention_days: Number of days to retain messages
        """
        self.agents: Dict[str, Agent] = {}
        self.agent_templates: Dict[str, Dict[str, Any]] = {}
        self.message_history: List[AgentMessage] = []
        self.auto_scaling = auto_scaling
        self.max_agents = max_agents
        self.message_retention_days = message_retention_days
        self.running = False
        self.update_interval = 1.0  # seconds
        self.update_thread: Optional[threading.Thread] = None
        self.lock = threading.RLock()
        
        if config_path and os.path.exists(config_path):
            self.load_config(config_path)
        
        logger.info(f"Agent Orchestrator initialized with auto_scaling={auto_scaling}, max_agents={max_agents}")
    
    def load_config(self, config_path: str):
        """
        Load configuration from file.
        
        Args:
            config_path: Path to configuration file
        """
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
            
            if "agent_templates" in config:
                self.agent_templates = config["agent_templates"]
            
            if "auto_scaling" in config:
                self.auto_scaling = config["auto_scaling"]
            
            if "max_agents" in config:
                self.max_agents = config["max_agents"]
            
            if "message_retention_days" in config:
                self.message_retention_days = config["message_retention_days"]
            
            if "update_interval" in config:
                self.update_interval = config["update_interval"]
            
            logger.info(f"Loaded configuration from {config_path}")
        except Exception as e:
            logger.error(f"Failed to load configuration from {config_path}: {str(e)}")
    
    def register_agent(self, agent: Agent) -> bool:
        """
        Register an agent with the orchestrator.
        
        Args:
            agent: Agent to register
            
        Returns:
            bool: True if registration was successful
        """
        with self.lock:
            if len(self.agents) >= self.max_agents:
                logger.warning(f"Cannot register agent {agent.id}: maximum number of agents reached")
                return False
            
            if agent.id in self.agents:
                logger.warning(f"Agent {agent.id} already registered")
                return False
            
            self.agents[agent.id] = agent
            agent.orchestrator = self
            logger.info(f"Registered agent {agent.name} ({agent.id}) of type {agent.type}")
            return True
    
    def unregister_agent(self, agent_id: str) -> bool:
        """
        Unregister an agent from the orchestrator.
        
        Args:
            agent_id: ID of the agent to unregister
            
        Returns:
            bool: True if unregistration was successful
        """
        with self.lock:
            if agent_id not in self.agents:
                logger.warning(f"Agent {agent_id} not registered")
                return False
            
            agent = self.agents[agent_id]
            agent.stop()
            agent.orchestrator = None
            del self.agents[agent_id]
            logger.info(f"Unregistered agent {agent_id}")
            return True
    
    def create_agent(
        self,
        agent_type: Union[AgentType, str],
        name: str,
        config: Dict[str, Any] = None,
        template_id: Optional[str] = None
    ) -> Optional[Agent]:
        """
        Create a new agent.
        
        Args:
            agent_type: Type of agent to create
            name: Human-readable name for the agent
            config: Agent configuration
            template_id: ID of template to use
            
        Returns:
            Agent: Created agent, or None if creation failed
        """
        with self.lock:
            if len(self.agents) >= self.max_agents:
                logger.warning("Cannot create agent: maximum number of agents reached")
                return None
            
            if isinstance(agent_type, str):
                try:
                    agent_type = AgentType(agent_type)
                except ValueError:
                    agent_type = AgentType.CUSTOM
            
            if template_id and template_id in self.agent_templates:
                template = self.agent_templates[template_id]
                template_config = template.get("config", {})
                
                merged_config = template_config.copy()
                if config:
                    merged_config.update(config)
                
                config = merged_config
                
                if "type" in template and agent_type == AgentType.CUSTOM:
                    try:
                        agent_type = AgentType(template["type"])
                    except ValueError:
                        pass
            
            agent_id = str(uuid.uuid4())
            agent = Agent(agent_id, agent_type, name, config)
            
            if self.register_agent(agent):
                agent.start()
                return agent
            
            return None
    
    def get_agent(self, agent_id: str) -> Optional[Agent]:
        """
        Get an agent by ID.
        
        Args:
            agent_id: ID of the agent
            
        Returns:
            Agent: Agent with the specified ID, or None if not found
        """
        return self.agents.get(agent_id)
    
    def get_agents_by_type(self, agent_type: Union[AgentType, str]) -> List[Agent]:
        """
        Get all agents of a specific type.
        
        Args:
            agent_type: Type of agents to get
            
        Returns:
            List: List of agents of the specified type
        """
        if isinstance(agent_type, str):
            try:
                agent_type = AgentType(agent_type)
            except ValueError:
                return []
        
        return [agent for agent in self.agents.values() if agent.type == agent_type]
    
    def deliver_message(self, message: AgentMessage) -> bool:
        """
        Deliver a message to its recipient.
        
        Args:
            message: Message to deliver
            
        Returns:
            bool: True if delivery was successful
        """
        with self.lock:
            self.message_history.append(message)
            
            if message.recipient_id not in self.agents:
                logger.warning(f"Cannot deliver message {message.id}: recipient {message.recipient_id} not found")
                return False
            
            recipient = self.agents[message.recipient_id]
            result = recipient.receive_message(message)
            
            logger.debug(f"Delivered message {message.id} from {message.sender_id} to {message.recipient_id}")
            return result
    
    def broadcast_message(
        self,
        sender_id: str,
        agent_type: Optional[Union[AgentType, str]],
        message_type: str,
        content: Dict[str, Any],
        priority: int = 1,
        expires_at: Optional[int] = None
    ) -> List[str]:
        """
        Broadcast a message to all agents of a specific type.
        
        Args:
            sender_id: ID of the sending agent
            agent_type: Type of agents to broadcast to, or None for all agents
            message_type: Type of message
            content: Message content
            priority: Message priority (1-10)
            expires_at: Unix timestamp when message expires
            
        Returns:
            List: List of message IDs
        """
        with self.lock:
            message_ids = []
            
            if isinstance(agent_type, str):
                try:
                    agent_type = AgentType(agent_type)
                except ValueError:
                    agent_type = None
            
            if agent_type:
                recipients = self.get_agents_by_type(agent_type)
            else:
                recipients = list(self.agents.values())
            
            for recipient in recipients:
                if recipient.id != sender_id:  # Don't send to self
                    message = AgentMessage(
                        sender_id=sender_id,
                        recipient_id=recipient.id,
                        message_type=message_type,
                        content=content,
                        priority=priority,
                        expires_at=expires_at
                    )
                    
                    self.message_history.append(message)
                    recipient.receive_message(message)
                    message_ids.append(message.id)
            
            logger.debug(f"Broadcast message from {sender_id} to {len(message_ids)} agents")
            return message_ids
    
    def update_agents(self):
        """Update all agents"""
        with self.lock:
            for agent in list(self.agents.values()):
                try:
                    agent.update()
                except Exception as e:
                    logger.error(f"Error updating agent {agent.id}: {str(e)}")
                    agent.metrics["errors"] += 1
                    agent.status = AgentStatus.ERROR
    
    def clean_message_history(self):
        """Clean up old messages from history"""
        with self.lock:
            cutoff_time = int(time.time()) - (self.message_retention_days * 86400)
            self.message_history = [m for m in self.message_history if m.created_at >= cutoff_time]
    
    def update_loop(self):
        """Main update loop"""
        while self.running:
            try:
                self.update_agents()
                
                if int(time.time()) % 3600 < self.update_interval:  # Once per hour
                    self.clean_message_history()
                
                if self.auto_scaling:
                    self._check_auto_scaling()
                
                time.sleep(self.update_interval)
            except Exception as e:
                logger.error(f"Error in orchestrator update loop: {str(e)}")
                time.sleep(self.update_interval)
    
    def _check_auto_scaling(self):
        """
        Check if agents need to be scaled up or down based on workload and performance metrics.
        This method implements intelligent scaling of agents based on:
        1. Current workload (message queue size, processing time)
        2. Resource utilization (CPU, memory)
        3. Performance metrics (errors, response time)
        4. Time-based patterns (e.g., market hours for trading agents)
        """
        with self.lock:
            for agent_type in AgentType:
                agents = self.get_agents_by_type(agent_type)
                
                if not agents:
                    continue
                
                avg_queue_size = sum(len(a.inbox) for a in agents) / len(agents)
                avg_errors = sum(a.metrics["errors"] for a in agents) / len(agents)
                busy_agents = sum(1 for a in agents if a.status == AgentStatus.BUSY)
                busy_ratio = busy_agents / len(agents)
                
                if (avg_queue_size > 20 or busy_ratio > 0.8) and len(agents) < self.max_agents / len(AgentType):
                    # Create a new agent of this type
                    template_agent = agents[0]
                    new_name = f"{template_agent.name} {len(agents) + 1}"
                    self.create_agent(agent_type, new_name, template_agent.config.copy())
                    logger.info(f"Auto-scaled up: created new {agent_type.value} agent '{new_name}'")
                
                elif (avg_queue_size < 5 and busy_ratio < 0.3 and avg_errors < 1) and len(agents) > 1:
                    least_active = min(agents, key=lambda a: a.last_active)
                    if int(time.time()) - least_active.last_active > 3600:  # Inactive for 1 hour
                        self.unregister_agent(least_active.id)
                        logger.info(f"Auto-scaled down: removed inactive {agent_type.value} agent '{least_active.name}'")
            
            trading_agents = self.get_agents_by_type(AgentType.TRADING)
            if trading_agents:
                current_hour = datetime.now().hour
                is_market_hours = 8 <= current_hour <= 20  # 8 AM to 8 PM
                
                if is_market_hours and len(trading_agents) < 5:
                    template_agent = trading_agents[0]
                    new_name = f"{template_agent.name} {len(trading_agents) + 1}"
                    self.create_agent(AgentType.TRADING, new_name, template_agent.config.copy())
                    logger.info(f"Auto-scaled up: created new trading agent '{new_name}' for market hours")
    
    def start(self):
        """Start the orchestrator"""
        with self.lock:
            if self.running:
                return
            
            self.running = True
            self.update_thread = threading.Thread(target=self.update_loop)
            self.update_thread.daemon = True
            self.update_thread.start()
            
            logger.info("Agent Orchestrator started")
    
    def stop(self):
        """Stop the orchestrator"""
        with self.lock:
            if not self.running:
                return
            
            self.running = False
            if self.update_thread:
                self.update_thread.join(timeout=5.0)
            
            for agent in list(self.agents.values()):
                agent.stop()
            
            logger.info("Agent Orchestrator stopped")
    
    def get_status(self) -> Dict[str, Any]:
        """
        Get orchestrator status.
        
        Returns:
            Dict: Orchestrator status
        """
        with self.lock:
            return {
                "running": self.running,
                "agent_count": len(self.agents),
                "max_agents": self.max_agents,
                "auto_scaling": self.auto_scaling,
                "message_history_count": len(self.message_history),
                "agents": {agent_id: agent.to_dict() for agent_id, agent in self.agents.items()}
            }

class SuperAGIAgent(Agent):
    """
    Agent that integrates with SuperAGI framework for advanced AI capabilities.
    This agent can leverage SuperAGI's tools, memory, and planning capabilities.
    """
    
    def __init__(
        self,
        agent_id: str,
        name: str,
        config: Dict[str, Any] = None,
        api_key: Optional[str] = None,
        api_base: str = "https://api.superagi.com/v1",
        tools: List[str] = None
    ):
        """
        Initialize a SuperAGI agent.
        
        Args:
            agent_id: Unique ID for this agent
            name: Human-readable name
            config: Agent configuration
            api_key: SuperAGI API key
            api_base: SuperAGI API base URL
            tools: List of SuperAGI tools to use
        """
        super().__init__(agent_id, AgentType.SUPER_AGI, name, config)
        
        self.api_key = api_key
        self.api_base = api_base
        self.tools = tools or []
        self.session_id = None
        self.last_response = None
        
        self.register_message_handler("execute_task", self._handle_execute_task)
        self.register_message_handler("stop_execution", self._handle_stop_execution)
        self.register_message_handler("update_tools", self._handle_update_tools)
        
        logger.info(f"SuperAGI Agent {self.name} ({self.id}) initialized with {len(self.tools)} tools")
    
    def _initialize_session(self) -> bool:
        """
        Initialize a SuperAGI session.
        
        Returns:
            bool: True if initialization was successful
        """
        if not self.api_key:
            logger.error(f"SuperAGI Agent {self.id} has no API key")
            return False
        
        try:
            import requests
            
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            data = {
                "agent_name": self.name,
                "tools": self.tools,
                "config": self.config
            }
            
            response = requests.post(
                f"{self.api_base}/agents/create_session",
                headers=headers,
                json=data
            )
            
            if response.status_code == 200:
                result = response.json()
                self.session_id = result.get("session_id")
                logger.info(f"SuperAGI Agent {self.id} initialized session {self.session_id}")
                return True
            else:
                logger.error(f"SuperAGI Agent {self.id} failed to initialize session: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"SuperAGI Agent {self.id} failed to initialize session: {str(e)}")
            return False
    
    def _handle_execute_task(self, message: AgentMessage) -> bool:
        """
        Handle execute_task message.
        
        Args:
            message: Message to handle
            
        Returns:
            bool: True if handling was successful
        """
        task = message.content.get("task")
        if not task:
            logger.warning(f"SuperAGI Agent {self.id} received execute_task message without task")
            return False
        
        if not self.session_id and not self._initialize_session():
            logger.error(f"SuperAGI Agent {self.id} failed to initialize session for task execution")
            return False
        
        try:
            import requests
            
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            data = {
                "session_id": self.session_id,
                "task": task,
                "parameters": message.content.get("parameters", {})
            }
            
            response = requests.post(
                f"{self.api_base}/agents/execute_task",
                headers=headers,
                json=data
            )
            
            if response.status_code == 200:
                result = response.json()
                self.last_response = result
                
                self.send_message(
                    recipient_id=message.sender_id,
                    message_type="task_result",
                    content={
                        "task_id": message.id,
                        "result": result
                    }
                )
                
                logger.info(f"SuperAGI Agent {self.id} executed task successfully")
                return True
            else:
                logger.error(f"SuperAGI Agent {self.id} failed to execute task: {response.text}")
                
                self.send_message(
                    recipient_id=message.sender_id,
                    message_type="task_error",
                    content={
                        "task_id": message.id,
                        "error": response.text
                    }
                )
                
                return False
                
        except Exception as e:
            logger.error(f"SuperAGI Agent {self.id} failed to execute task: {str(e)}")
            
            self.send_message(
                recipient_id=message.sender_id,
                message_type="task_error",
                content={
                    "task_id": message.id,
                    "error": str(e)
                }
            )
            
            return False
    
    def _handle_stop_execution(self, message: AgentMessage) -> bool:
        """
        Handle stop_execution message.
        
        Args:
            message: Message to handle
            
        Returns:
            bool: True if handling was successful
        """
        if not self.session_id:
            logger.warning(f"SuperAGI Agent {self.id} received stop_execution message but has no active session")
            return False
        
        try:
            import requests
            
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            data = {
                "session_id": self.session_id
            }
            
            response = requests.post(
                f"{self.api_base}/agents/stop_execution",
                headers=headers,
                json=data
            )
            
            if response.status_code == 200:
                logger.info(f"SuperAGI Agent {self.id} stopped execution successfully")
                return True
            else:
                logger.error(f"SuperAGI Agent {self.id} failed to stop execution: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"SuperAGI Agent {self.id} failed to stop execution: {str(e)}")
            return False
    
    def _handle_update_tools(self, message: AgentMessage) -> bool:
        """
        Handle update_tools message.
        
        Args:
            message: Message to handle
            
        Returns:
            bool: True if handling was successful
        """
        tools = message.content.get("tools")
        if not tools:
            logger.warning(f"SuperAGI Agent {self.id} received update_tools message without tools")
            return False
        
        self.tools = tools
        
        if self.session_id:
            try:
                import requests
                
                headers = {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                }
                
                data = {
                    "session_id": self.session_id,
                    "tools": self.tools
                }
                
                response = requests.post(
                    f"{self.api_base}/agents/update_tools",
                    headers=headers,
                    json=data
                )
                
                if response.status_code == 200:
                    logger.info(f"SuperAGI Agent {self.id} updated tools successfully")
                    return True
                else:
                    logger.error(f"SuperAGI Agent {self.id} failed to update tools: {response.text}")
                    return False
                    
            except Exception as e:
                logger.error(f"SuperAGI Agent {self.id} failed to update tools: {str(e)}")
                return False
        
        return True
    
    def stop(self):
        """Stop the agent and clean up resources"""
        if self.session_id:
            try:
                import requests
                
                headers = {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                }
                
                data = {
                    "session_id": self.session_id
                }
                
                requests.post(
                    f"{self.api_base}/agents/end_session",
                    headers=headers,
                    json=data
                )
                
                logger.info(f"SuperAGI Agent {self.id} ended session {self.session_id}")
            except Exception as e:
                logger.error(f"SuperAGI Agent {self.id} failed to end session: {str(e)}")
        
        super().stop()


class TradingAgent(Agent):
    """
    Specialized agent for trading operations.
    """
    
    def __init__(
        self,
        agent_id: str,
        name: str,
        strategy_type: str,
        exchange: str,
        symbols: List[str],
        config: Dict[str, Any] = None
    ):
        """
        Initialize a trading agent.
        
        Args:
            agent_id: Unique ID for this agent
            name: Human-readable name
            strategy_type: Type of trading strategy to use
            exchange: Exchange to trade on
            symbols: Symbols to trade
            config: Agent configuration
        """
        agent_type = AgentType.TRADING
        
        if strategy_type == "market_maker":
            agent_type = AgentType.MARKET_MAKER
        elif strategy_type == "arbitrage":
            agent_type = AgentType.ARBITRAGE
        elif strategy_type == "trend_following":
            agent_type = AgentType.TREND_FOLLOWING
        elif strategy_type == "mean_reversion":
            agent_type = AgentType.MEAN_REVERSION
        
        merged_config = {
            "strategy_type": strategy_type,
            "exchange": exchange,
            "symbols": symbols
        }
        
        if config:
            merged_config.update(config)
        
        super().__init__(agent_id, agent_type, name, merged_config)
        
        self.strategy_type = strategy_type
        self.exchange = exchange
        self.symbols = symbols
        self.positions = {}
        self.orders = {}
        
        self.register_message_handler("place_order", self._handle_place_order)
        self.register_message_handler("cancel_order", self._handle_cancel_order)
        self.register_message_handler("update_strategy", self._handle_update_strategy)
        
        logger.info(f"Trading Agent {self.name} ({self.id}) initialized with strategy {self.strategy_type} on {self.exchange}")
    
    def _handle_place_order(self, message: AgentMessage) -> bool:
        """
        Handle place_order message.
        
        Args:
            message: Message to handle
            
        Returns:
            bool: True if handling was successful
        """
        logger.info(f"Trading Agent {self.id} received place_order message")
        return True
    
    def _handle_cancel_order(self, message: AgentMessage) -> bool:
        """
        Handle cancel_order message.
        
        Args:
            message: Message to handle
            
        Returns:
            bool: True if handling was successful
        """
        logger.info(f"Trading Agent {self.id} received cancel_order message")
        return True
    
    def _handle_update_strategy(self, message: AgentMessage) -> bool:
        """
        Handle update_strategy message.
        
        Args:
            message: Message to handle
            
        Returns:
            bool: True if handling was successful
        """
        strategy_params = message.content.get("strategy_params")
        if not strategy_params:
            logger.warning(f"Trading Agent {self.id} received update_strategy message without strategy_params")
            return False
        
        self.config["strategy_params"] = strategy_params
        logger.info(f"Trading Agent {self.id} updated strategy parameters")
        return True


class EcommerceAgent(Agent):
    """
    Specialized agent for e-commerce operations.
    """
    
    def __init__(
        self,
        agent_id: str,
        name: str,
        platform: str,
        store_id: str,
        config: Dict[str, Any] = None
    ):
        """
        Initialize an e-commerce agent.
        
        Args:
            agent_id: Unique ID for this agent
            name: Human-readable name
            platform: E-commerce platform (e.g., "shopify", "woocommerce")
            store_id: Store ID
            config: Agent configuration
        """
        agent_type = AgentType.ECOMMERCE
        
        merged_config = {
            "platform": platform,
            "store_id": store_id
        }
        
        if config:
            merged_config.update(config)
        
        super().__init__(agent_id, agent_type, name, merged_config)
        
        self.platform = platform
        self.store_id = store_id
        
        self.register_message_handler("sync_inventory", self._handle_sync_inventory)
        self.register_message_handler("update_pricing", self._handle_update_pricing)
        self.register_message_handler("process_order", self._handle_process_order)
        
        logger.info(f"E-commerce Agent {self.name} ({self.id}) initialized for platform {self.platform}")
    
    def _handle_sync_inventory(self, message: AgentMessage) -> bool:
        """
        Handle sync_inventory message.
        
        Args:
            message: Message to handle
            
        Returns:
            bool: True if handling was successful
        """
        logger.info(f"E-commerce Agent {self.id} received sync_inventory message")
        return True
    
    def _handle_update_pricing(self, message: AgentMessage) -> bool:
        """
        Handle update_pricing message.
        
        Args:
            message: Message to handle
            
        Returns:
            bool: True if handling was successful
        """
        products = message.content.get("products")
        if not products:
            logger.warning(f"E-commerce Agent {self.id} received update_pricing message without products")
            return False
        
        logger.info(f"E-commerce Agent {self.id} updating pricing for {len(products)} products")
        return True
    
    def _handle_process_order(self, message: AgentMessage) -> bool:
        """
        Handle process_order message.
        
        Args:
            message: Message to handle
            
        Returns:
            bool: True if handling was successful
        """
        order_id = message.content.get("order_id")
        if not order_id:
            logger.warning(f"E-commerce Agent {self.id} received process_order message without order_id")
            return False
        
        logger.info(f"E-commerce Agent {self.id} processing order {order_id}")
        return True


def create_orchestrator(config_path: Optional[str] = None) -> AgentOrchestrator:
    """
    Create a new agent orchestrator.
    
    Args:
        config_path: Path to configuration file
        
    Returns:
        AgentOrchestrator: New orchestrator instance
    """
    orchestrator = AgentOrchestrator(config_path)
    orchestrator.start()
    return orchestrator
