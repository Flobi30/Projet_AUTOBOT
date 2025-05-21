"""
Agent orchestration package for AUTOBOT.

This package provides the agent orchestration system for AUTOBOT,
including the base Agent class, AgentOrchestrator, and specialized agents.
"""

from .orchestrator import (
    Agent,
    AgentType,
    AgentStatus,
    AgentMessage,
    AgentOrchestrator,
    SuperAGIAgent,
    TradingAgent,
    EcommerceAgent
)

from .specialized_agents import (
    RLAgent,
    SecurityAgent,
    MonitoringAgent,
    PredictionAgent
)

from .autobot_master import (
    AutobotMasterAgent,
    create_autobot_master_agent
)

__all__ = [
    'Agent',
    'AgentType',
    'AgentStatus',
    'AgentMessage',
    'AgentOrchestrator',
    'SuperAGIAgent',
    'TradingAgent',
    'EcommerceAgent',
    'RLAgent',
    'SecurityAgent',
    'MonitoringAgent',
    'PredictionAgent',
    'AutobotMasterAgent',
    'create_autobot_master_agent'
]
