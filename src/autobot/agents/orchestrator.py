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
        """Check if agents need to be scaled up or down"""
        pass
    
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
