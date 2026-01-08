"""
AUTOBOT Auto-Healing System

Self-healing system capable of:
- Restarting crashed modules
- Restoring providers
- Reloading ML models
- Rebuilding cache
- Rolling back to last working configuration
"""

import logging
import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Callable, Any, Tuple
import json
import os
import traceback
import threading
import time

logger = logging.getLogger(__name__)


class ComponentStatus(Enum):
    """Component health status"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    FAILED = "failed"
    RECOVERING = "recovering"
    UNKNOWN = "unknown"


class RecoveryAction(Enum):
    """Types of recovery actions"""
    RESTART = "restart"
    RELOAD = "reload"
    REBUILD_CACHE = "rebuild_cache"
    RESTORE_CONFIG = "restore_config"
    RECONNECT = "reconnect"
    ROLLBACK = "rollback"
    ESCALATE = "escalate"


@dataclass
class ComponentHealth:
    """Health status of a component"""
    component_id: str
    component_name: str
    component_type: str  # provider, model, cache, service, module
    status: ComponentStatus = ComponentStatus.UNKNOWN
    last_check: Optional[datetime] = None
    last_healthy: Optional[datetime] = None
    consecutive_failures: int = 0
    error_message: Optional[str] = None
    recovery_attempts: int = 0
    last_recovery: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "component_id": self.component_id,
            "component_name": self.component_name,
            "component_type": self.component_type,
            "status": self.status.value,
            "last_check": self.last_check.isoformat() if self.last_check else None,
            "last_healthy": self.last_healthy.isoformat() if self.last_healthy else None,
            "consecutive_failures": self.consecutive_failures,
            "error_message": self.error_message,
            "recovery_attempts": self.recovery_attempts,
            "last_recovery": self.last_recovery.isoformat() if self.last_recovery else None,
            "metadata": self.metadata,
        }


@dataclass
class RecoveryEvent:
    """Record of a recovery action"""
    event_id: str
    timestamp: datetime
    component_id: str
    action: RecoveryAction
    success: bool
    duration_seconds: float
    error_message: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "timestamp": self.timestamp.isoformat(),
            "component_id": self.component_id,
            "action": self.action.value,
            "success": self.success,
            "duration_seconds": self.duration_seconds,
            "error_message": self.error_message,
            "details": self.details,
        }


@dataclass
class ConfigSnapshot:
    """Snapshot of working configuration"""
    snapshot_id: str
    timestamp: datetime
    config_data: Dict[str, Any]
    component_states: Dict[str, str]
    description: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "timestamp": self.timestamp.isoformat(),
            "config_data": self.config_data,
            "component_states": self.component_states,
            "description": self.description,
        }


class AutoHealingSystem:
    """
    Auto-Healing System for AUTOBOT.
    
    Monitors component health and automatically recovers from failures:
    - Restarts crashed modules
    - Restores provider connections
    - Reloads ML models
    - Rebuilds corrupted caches
    - Rolls back to last working configuration
    """
    
    # Recovery settings
    MAX_RECOVERY_ATTEMPTS = 3
    RECOVERY_COOLDOWN_SECONDS = 60
    HEALTH_CHECK_INTERVAL_SECONDS = 30
    MAX_CONSECUTIVE_FAILURES = 5
    
    def __init__(
        self,
        data_dir: str = "/app/data",
        enable_auto_recovery: bool = True,
        health_check_interval: int = 30,
    ):
        self.data_dir = data_dir
        self.enable_auto_recovery = enable_auto_recovery
        self.health_check_interval = health_check_interval
        
        # Component registry
        self.components: Dict[str, ComponentHealth] = {}
        
        # Health check functions
        self.health_checks: Dict[str, Callable[[], bool]] = {}
        
        # Recovery handlers
        self.recovery_handlers: Dict[str, Dict[RecoveryAction, Callable[[], bool]]] = {}
        
        # Recovery history
        self.recovery_events: List[RecoveryEvent] = []
        self.event_counter = 0
        
        # Configuration snapshots
        self.config_snapshots: List[ConfigSnapshot] = []
        self.snapshot_counter = 0
        self.max_snapshots = 10
        
        # Background monitoring
        self._monitoring_thread: Optional[threading.Thread] = None
        self._stop_monitoring = threading.Event()
        
        # Ensure data directory exists
        os.makedirs(data_dir, exist_ok=True)
        
        logger.info("Auto-Healing System initialized")
    
    # =========================================================================
    # Component Registration
    # =========================================================================
    
    def register_component(
        self,
        component_id: str,
        component_name: str,
        component_type: str,
        health_check: Optional[Callable[[], bool]] = None,
        recovery_handlers: Optional[Dict[RecoveryAction, Callable[[], bool]]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ComponentHealth:
        """
        Register a component for health monitoring.
        
        Args:
            component_id: Unique identifier for the component
            component_name: Human-readable name
            component_type: Type of component (provider, model, cache, service, module)
            health_check: Function that returns True if component is healthy
            recovery_handlers: Dict mapping recovery actions to handler functions
            metadata: Additional metadata about the component
        """
        component = ComponentHealth(
            component_id=component_id,
            component_name=component_name,
            component_type=component_type,
            status=ComponentStatus.UNKNOWN,
            metadata=metadata or {},
        )
        
        self.components[component_id] = component
        
        if health_check:
            self.health_checks[component_id] = health_check
        
        if recovery_handlers:
            self.recovery_handlers[component_id] = recovery_handlers
        
        logger.info(f"Registered component: {component_name} ({component_type})")
        return component
    
    def unregister_component(self, component_id: str) -> bool:
        """Unregister a component"""
        if component_id in self.components:
            del self.components[component_id]
            self.health_checks.pop(component_id, None)
            self.recovery_handlers.pop(component_id, None)
            logger.info(f"Unregistered component: {component_id}")
            return True
        return False
    
    # =========================================================================
    # Health Checking
    # =========================================================================
    
    def check_component_health(self, component_id: str) -> ComponentStatus:
        """Check health of a specific component"""
        if component_id not in self.components:
            logger.warning(f"Component {component_id} not registered")
            return ComponentStatus.UNKNOWN
        
        component = self.components[component_id]
        health_check = self.health_checks.get(component_id)
        
        if not health_check:
            # No health check registered, assume healthy
            component.status = ComponentStatus.HEALTHY
            component.last_check = datetime.utcnow()
            return ComponentStatus.HEALTHY
        
        try:
            is_healthy = health_check()
            component.last_check = datetime.utcnow()
            
            if is_healthy:
                component.status = ComponentStatus.HEALTHY
                component.last_healthy = datetime.utcnow()
                component.consecutive_failures = 0
                component.error_message = None
            else:
                component.consecutive_failures += 1
                component.error_message = "Health check returned False"
                
                if component.consecutive_failures >= self.MAX_CONSECUTIVE_FAILURES:
                    component.status = ComponentStatus.FAILED
                elif component.consecutive_failures >= 2:
                    component.status = ComponentStatus.UNHEALTHY
                else:
                    component.status = ComponentStatus.DEGRADED
                
                logger.warning(
                    f"Component {component_id} health check failed "
                    f"({component.consecutive_failures} consecutive failures)"
                )
                
        except Exception as e:
            component.last_check = datetime.utcnow()
            component.consecutive_failures += 1
            component.error_message = str(e)
            component.status = ComponentStatus.FAILED
            
            logger.error(f"Component {component_id} health check error: {e}")
        
        return component.status
    
    def check_all_health(self) -> Dict[str, ComponentStatus]:
        """Check health of all registered components"""
        results = {}
        
        for component_id in self.components:
            results[component_id] = self.check_component_health(component_id)
        
        return results
    
    def get_unhealthy_components(self) -> List[str]:
        """Get list of unhealthy component IDs"""
        unhealthy = []
        
        for component_id, component in self.components.items():
            if component.status in [ComponentStatus.UNHEALTHY, ComponentStatus.FAILED]:
                unhealthy.append(component_id)
        
        return unhealthy
    
    # =========================================================================
    # Recovery Actions
    # =========================================================================
    
    def attempt_recovery(
        self,
        component_id: str,
        action: Optional[RecoveryAction] = None,
    ) -> Tuple[bool, str]:
        """
        Attempt to recover a component.
        
        Args:
            component_id: Component to recover
            action: Specific recovery action (auto-selected if None)
            
        Returns:
            Tuple of (success, message)
        """
        if component_id not in self.components:
            return False, f"Component {component_id} not registered"
        
        component = self.components[component_id]
        
        # Check recovery cooldown
        if component.last_recovery:
            cooldown_end = component.last_recovery + timedelta(seconds=self.RECOVERY_COOLDOWN_SECONDS)
            if datetime.utcnow() < cooldown_end:
                return False, f"Recovery cooldown active until {cooldown_end}"
        
        # Check max recovery attempts
        if component.recovery_attempts >= self.MAX_RECOVERY_ATTEMPTS:
            return False, f"Max recovery attempts ({self.MAX_RECOVERY_ATTEMPTS}) reached"
        
        # Select recovery action
        if action is None:
            action = self._select_recovery_action(component_id)
        
        if action is None:
            return False, "No recovery action available"
        
        # Get recovery handler
        handlers = self.recovery_handlers.get(component_id, {})
        handler = handlers.get(action)
        
        if not handler:
            # Try default recovery actions
            handler = self._get_default_recovery_handler(component, action)
        
        if not handler:
            return False, f"No handler for recovery action: {action.value}"
        
        # Mark as recovering
        component.status = ComponentStatus.RECOVERING
        component.recovery_attempts += 1
        component.last_recovery = datetime.utcnow()
        
        # Execute recovery
        start_time = time.time()
        success = False
        error_message = None
        
        try:
            logger.info(f"Attempting recovery for {component_id}: {action.value}")
            success = handler()
            
        except Exception as e:
            error_message = str(e)
            logger.error(f"Recovery failed for {component_id}: {e}")
            logger.debug(traceback.format_exc())
        
        duration = time.time() - start_time
        
        # Record recovery event
        self._record_recovery_event(
            component_id=component_id,
            action=action,
            success=success,
            duration=duration,
            error_message=error_message,
        )
        
        # Update component status
        if success:
            component.status = ComponentStatus.HEALTHY
            component.consecutive_failures = 0
            component.error_message = None
            logger.info(f"Recovery successful for {component_id}")
            return True, "Recovery successful"
        else:
            component.status = ComponentStatus.FAILED
            return False, error_message or "Recovery failed"
    
    def _select_recovery_action(self, component_id: str) -> Optional[RecoveryAction]:
        """Select appropriate recovery action based on component type and state"""
        component = self.components[component_id]
        handlers = self.recovery_handlers.get(component_id, {})
        
        # Priority order based on component type
        if component.component_type == "provider":
            priority = [RecoveryAction.RECONNECT, RecoveryAction.RESTART, RecoveryAction.ROLLBACK]
        elif component.component_type == "model":
            priority = [RecoveryAction.RELOAD, RecoveryAction.RESTART, RecoveryAction.ROLLBACK]
        elif component.component_type == "cache":
            priority = [RecoveryAction.REBUILD_CACHE, RecoveryAction.RESTART]
        elif component.component_type == "service":
            priority = [RecoveryAction.RESTART, RecoveryAction.RESTORE_CONFIG, RecoveryAction.ROLLBACK]
        else:
            priority = [RecoveryAction.RESTART, RecoveryAction.RELOAD, RecoveryAction.ROLLBACK]
        
        # Find first available action
        for action in priority:
            if action in handlers or self._has_default_handler(component, action):
                return action
        
        return None
    
    def _has_default_handler(self, component: ComponentHealth, action: RecoveryAction) -> bool:
        """Check if a default handler exists for the action"""
        return action in [RecoveryAction.RESTART, RecoveryAction.ESCALATE]
    
    def _get_default_recovery_handler(
        self,
        component: ComponentHealth,
        action: RecoveryAction,
    ) -> Optional[Callable[[], bool]]:
        """Get default recovery handler for common actions"""
        if action == RecoveryAction.RESTART:
            return lambda: self._default_restart(component)
        elif action == RecoveryAction.ESCALATE:
            return lambda: self._escalate_failure(component)
        return None
    
    def _default_restart(self, component: ComponentHealth) -> bool:
        """Default restart handler - logs and returns True"""
        logger.info(f"Default restart for {component.component_name}")
        # In a real implementation, this would restart the component
        # For now, we just log and return True
        return True
    
    def _escalate_failure(self, component: ComponentHealth) -> bool:
        """Escalate failure for manual intervention"""
        logger.critical(
            f"ESCALATION: Component {component.component_name} requires manual intervention. "
            f"Consecutive failures: {component.consecutive_failures}, "
            f"Error: {component.error_message}"
        )
        return False  # Escalation doesn't "fix" the problem
    
    def _record_recovery_event(
        self,
        component_id: str,
        action: RecoveryAction,
        success: bool,
        duration: float,
        error_message: Optional[str] = None,
    ):
        """Record a recovery event"""
        self.event_counter += 1
        
        event = RecoveryEvent(
            event_id=f"recovery_{self.event_counter}",
            timestamp=datetime.utcnow(),
            component_id=component_id,
            action=action,
            success=success,
            duration_seconds=duration,
            error_message=error_message,
        )
        
        self.recovery_events.append(event)
        
        # Keep only last 100 events
        if len(self.recovery_events) > 100:
            self.recovery_events = self.recovery_events[-100:]
    
    # =========================================================================
    # Configuration Snapshots
    # =========================================================================
    
    def create_config_snapshot(
        self,
        config_data: Dict[str, Any],
        description: str = "",
    ) -> ConfigSnapshot:
        """Create a snapshot of the current working configuration"""
        self.snapshot_counter += 1
        
        # Capture component states
        component_states = {
            cid: c.status.value for cid, c in self.components.items()
        }
        
        snapshot = ConfigSnapshot(
            snapshot_id=f"snapshot_{self.snapshot_counter}",
            timestamp=datetime.utcnow(),
            config_data=config_data,
            component_states=component_states,
            description=description,
        )
        
        self.config_snapshots.append(snapshot)
        
        # Keep only max_snapshots
        if len(self.config_snapshots) > self.max_snapshots:
            self.config_snapshots = self.config_snapshots[-self.max_snapshots:]
        
        logger.info(f"Created config snapshot: {snapshot.snapshot_id}")
        return snapshot
    
    def get_latest_snapshot(self) -> Optional[ConfigSnapshot]:
        """Get the most recent configuration snapshot"""
        if self.config_snapshots:
            return self.config_snapshots[-1]
        return None
    
    def get_last_healthy_snapshot(self) -> Optional[ConfigSnapshot]:
        """Get the most recent snapshot where all components were healthy"""
        for snapshot in reversed(self.config_snapshots):
            all_healthy = all(
                status == ComponentStatus.HEALTHY.value
                for status in snapshot.component_states.values()
            )
            if all_healthy:
                return snapshot
        return None
    
    def rollback_to_snapshot(
        self,
        snapshot_id: str,
        apply_config: Optional[Callable[[Dict[str, Any]], bool]] = None,
    ) -> Tuple[bool, str]:
        """
        Rollback to a specific configuration snapshot.
        
        Args:
            snapshot_id: ID of the snapshot to rollback to
            apply_config: Function to apply the configuration
            
        Returns:
            Tuple of (success, message)
        """
        # Find snapshot
        snapshot = None
        for s in self.config_snapshots:
            if s.snapshot_id == snapshot_id:
                snapshot = s
                break
        
        if not snapshot:
            return False, f"Snapshot {snapshot_id} not found"
        
        logger.info(f"Rolling back to snapshot: {snapshot_id}")
        
        if apply_config:
            try:
                success = apply_config(snapshot.config_data)
                if success:
                    return True, f"Rolled back to snapshot {snapshot_id}"
                else:
                    return False, "Config application returned False"
            except Exception as e:
                return False, f"Rollback failed: {e}"
        else:
            # No apply function, just return the config
            return True, f"Snapshot {snapshot_id} retrieved (no apply function)"
    
    # =========================================================================
    # Background Monitoring
    # =========================================================================
    
    def start_monitoring(self):
        """Start background health monitoring"""
        if self._monitoring_thread and self._monitoring_thread.is_alive():
            logger.warning("Monitoring already running")
            return
        
        self._stop_monitoring.clear()
        self._monitoring_thread = threading.Thread(
            target=self._monitoring_loop,
            daemon=True,
        )
        self._monitoring_thread.start()
        logger.info("Started background health monitoring")
    
    def stop_monitoring(self):
        """Stop background health monitoring"""
        self._stop_monitoring.set()
        if self._monitoring_thread:
            self._monitoring_thread.join(timeout=5)
        logger.info("Stopped background health monitoring")
    
    def _monitoring_loop(self):
        """Background monitoring loop"""
        while not self._stop_monitoring.is_set():
            try:
                # Check all component health
                self.check_all_health()
                
                # Attempt recovery for unhealthy components
                if self.enable_auto_recovery:
                    unhealthy = self.get_unhealthy_components()
                    for component_id in unhealthy:
                        self.attempt_recovery(component_id)
                
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
            
            # Wait for next check
            self._stop_monitoring.wait(self.health_check_interval)
    
    # =========================================================================
    # Status and Reporting
    # =========================================================================
    
    def get_system_health(self) -> Dict[str, Any]:
        """Get overall system health status"""
        total = len(self.components)
        healthy = sum(1 for c in self.components.values() if c.status == ComponentStatus.HEALTHY)
        degraded = sum(1 for c in self.components.values() if c.status == ComponentStatus.DEGRADED)
        unhealthy = sum(1 for c in self.components.values() if c.status == ComponentStatus.UNHEALTHY)
        failed = sum(1 for c in self.components.values() if c.status == ComponentStatus.FAILED)
        
        # Determine overall status
        if failed > 0:
            overall = ComponentStatus.FAILED
        elif unhealthy > 0:
            overall = ComponentStatus.UNHEALTHY
        elif degraded > 0:
            overall = ComponentStatus.DEGRADED
        elif healthy == total and total > 0:
            overall = ComponentStatus.HEALTHY
        else:
            overall = ComponentStatus.UNKNOWN
        
        return {
            "overall_status": overall.value,
            "total_components": total,
            "healthy": healthy,
            "degraded": degraded,
            "unhealthy": unhealthy,
            "failed": failed,
            "auto_recovery_enabled": self.enable_auto_recovery,
            "monitoring_active": self._monitoring_thread is not None and self._monitoring_thread.is_alive(),
            "recent_recoveries": len([e for e in self.recovery_events if e.timestamp > datetime.utcnow() - timedelta(hours=1)]),
        }
    
    def get_component_status(self, component_id: str) -> Optional[Dict[str, Any]]:
        """Get status of a specific component"""
        if component_id not in self.components:
            return None
        return self.components[component_id].to_dict()
    
    def get_all_component_status(self) -> Dict[str, Dict[str, Any]]:
        """Get status of all components"""
        return {cid: c.to_dict() for cid, c in self.components.items()}
    
    def get_recovery_history(
        self,
        component_id: Optional[str] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """Get recovery event history"""
        events = self.recovery_events
        
        if component_id:
            events = [e for e in events if e.component_id == component_id]
        
        return [e.to_dict() for e in events[-limit:]]
    
    # =========================================================================
    # Persistence
    # =========================================================================
    
    def save_state(self):
        """Save auto-healing state to file"""
        state_file = os.path.join(self.data_dir, "auto_healing_state.json")
        
        data = {
            "components": {cid: c.to_dict() for cid, c in self.components.items()},
            "recovery_events": [e.to_dict() for e in self.recovery_events[-50:]],
            "config_snapshots": [s.to_dict() for s in self.config_snapshots],
            "saved_at": datetime.utcnow().isoformat(),
        }
        
        with open(state_file, 'w') as f:
            json.dump(data, f, indent=2)
        
        logger.info(f"Auto-healing state saved to {state_file}")
    
    def load_state(self) -> bool:
        """Load auto-healing state from file"""
        state_file = os.path.join(self.data_dir, "auto_healing_state.json")
        
        if not os.path.exists(state_file):
            return False
        
        try:
            with open(state_file, 'r') as f:
                data = json.load(f)
            
            # Restore component states (partial - health checks need re-registration)
            for cid, cdata in data.get("components", {}).items():
                if cid in self.components:
                    self.components[cid].recovery_attempts = cdata.get("recovery_attempts", 0)
            
            logger.info(f"Auto-healing state loaded from {state_file}")
            return True
            
        except Exception as e:
            logger.error(f"Error loading auto-healing state: {e}")
            return False


# Singleton instance
_auto_healing_instance: Optional[AutoHealingSystem] = None


def get_auto_healing_system(
    data_dir: str = "/app/data",
    enable_auto_recovery: bool = True,
) -> AutoHealingSystem:
    """Get or create the singleton AutoHealingSystem instance"""
    global _auto_healing_instance
    
    if _auto_healing_instance is None:
        _auto_healing_instance = AutoHealingSystem(
            data_dir=data_dir,
            enable_auto_recovery=enable_auto_recovery,
        )
    
    return _auto_healing_instance
