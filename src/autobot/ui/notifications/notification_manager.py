"""
Notification manager for AUTOBOT UI.
Handles the creation, display, and management of notifications.
"""
import json
import logging
import uuid
from enum import Enum
from typing import Dict, List, Optional, Any, Union
from datetime import datetime

logger = logging.getLogger(__name__)

class NotificationType(str, Enum):
    """Notification types."""
    SUCCESS = "success"
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"

class NotificationPosition(str, Enum):
    """Notification positions."""
    TOP_RIGHT = "top-right"
    TOP_LEFT = "top-left"
    BOTTOM_RIGHT = "bottom-right"
    BOTTOM_LEFT = "bottom-left"
    TOP_CENTER = "top-center"
    BOTTOM_CENTER = "bottom-center"

class Notification:
    """
    Notification class representing a single notification.
    """
    
    def __init__(
        self,
        message: str,
        type: NotificationType = NotificationType.INFO,
        title: Optional[str] = None,
        duration: int = 5000,
        position: NotificationPosition = NotificationPosition.TOP_RIGHT,
        closable: bool = True,
        auto_close: bool = True,
        icon: Optional[str] = None,
        data: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize a notification.
        
        Args:
            message: Notification message
            type: Notification type
            title: Optional notification title
            duration: Display duration in milliseconds
            position: Display position
            closable: Whether the notification can be closed manually
            auto_close: Whether the notification should close automatically
            icon: Optional icon for the notification
            data: Optional additional data
        """
        self.id = str(uuid.uuid4())
        self.message = message
        self.type = type
        self.title = title
        self.duration = duration
        self.position = position
        self.closable = closable
        self.auto_close = auto_close
        self.icon = icon
        self.data = data or {}
        self.created_at = datetime.now().isoformat()
        self.read = False
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert notification to dictionary.
        
        Returns:
            Dict representation of the notification
        """
        return {
            "id": self.id,
            "message": self.message,
            "type": self.type,
            "title": self.title,
            "duration": self.duration,
            "position": self.position,
            "closable": self.closable,
            "auto_close": self.auto_close,
            "icon": self.icon,
            "data": self.data,
            "created_at": self.created_at,
            "read": self.read
        }
    
    def to_json(self) -> str:
        """
        Convert notification to JSON.
        
        Returns:
            JSON representation of the notification
        """
        return json.dumps(self.to_dict())
    
    def mark_as_read(self) -> None:
        """Mark the notification as read."""
        self.read = True

class NotificationManager:
    """
    Notification manager for handling notifications.
    """
    
    def __init__(self):
        """Initialize the notification manager."""
        self.notifications: Dict[str, Notification] = {}
        self.history: List[Notification] = []
        self.max_history = 100
    
    def create_notification(
        self,
        message: str,
        type: Union[NotificationType, str] = NotificationType.INFO,
        title: Optional[str] = None,
        duration: int = 5000,
        position: Union[NotificationPosition, str] = NotificationPosition.TOP_RIGHT,
        closable: bool = True,
        auto_close: bool = True,
        icon: Optional[str] = None,
        data: Optional[Dict[str, Any]] = None
    ) -> Notification:
        """
        Create a new notification.
        
        Args:
            message: Notification message
            type: Notification type
            title: Optional notification title
            duration: Display duration in milliseconds
            position: Display position
            closable: Whether the notification can be closed manually
            auto_close: Whether the notification should close automatically
            icon: Optional icon for the notification
            data: Optional additional data
            
        Returns:
            Created notification
        """
        if isinstance(type, str):
            type = NotificationType(type)
        
        if isinstance(position, str):
            position = NotificationPosition(position)
        
        notification = Notification(
            message=message,
            type=type,
            title=title,
            duration=duration,
            position=position,
            closable=closable,
            auto_close=auto_close,
            icon=icon,
            data=data
        )
        
        self.notifications[notification.id] = notification
        
        self.history.append(notification)
        
        if len(self.history) > self.max_history:
            self.history = self.history[-self.max_history:]
        
        logger.info(f"Created notification: {notification.id} - {notification.message}")
        
        return notification
    
    def get_notification(self, notification_id: str) -> Optional[Notification]:
        """
        Get a notification by ID.
        
        Args:
            notification_id: Notification ID
            
        Returns:
            Notification if found, None otherwise
        """
        return self.notifications.get(notification_id)
    
    def remove_notification(self, notification_id: str) -> bool:
        """
        Remove a notification by ID.
        
        Args:
            notification_id: Notification ID
            
        Returns:
            True if removed, False otherwise
        """
        if notification_id in self.notifications:
            notification = self.notifications.pop(notification_id)
            logger.info(f"Removed notification: {notification_id}")
            return True
        return False
    
    def clear_notifications(self) -> None:
        """Clear all active notifications."""
        self.notifications = {}
        logger.info("Cleared all notifications")
    
    def get_active_notifications(self) -> List[Notification]:
        """
        Get all active notifications.
        
        Returns:
            List of active notifications
        """
        return list(self.notifications.values())
    
    def get_notification_history(self, limit: Optional[int] = None) -> List[Notification]:
        """
        Get notification history.
        
        Args:
            limit: Optional limit on number of notifications to return
            
        Returns:
            List of historical notifications
        """
        if limit is not None:
            return self.history[-limit:]
        return self.history
    
    def mark_as_read(self, notification_id: str) -> bool:
        """
        Mark a notification as read.
        
        Args:
            notification_id: Notification ID
            
        Returns:
            True if marked as read, False otherwise
        """
        notification = self.get_notification(notification_id)
        if notification:
            notification.mark_as_read()
            return True
        return False
    
    def mark_all_as_read(self) -> None:
        """Mark all notifications as read."""
        for notification in self.notifications.values():
            notification.mark_as_read()

_notification_manager = NotificationManager()

def get_notification_manager() -> NotificationManager:
    """
    Get the global notification manager instance.
    
    Returns:
        NotificationManager instance
    """
    return _notification_manager

def create_notification(
    message: str,
    type: Union[NotificationType, str] = NotificationType.INFO,
    title: Optional[str] = None,
    duration: int = 5000,
    position: Union[NotificationPosition, str] = NotificationPosition.TOP_RIGHT,
    closable: bool = True,
    auto_close: bool = True,
    icon: Optional[str] = None,
    data: Optional[Dict[str, Any]] = None
) -> Notification:
    """
    Create a notification using the global notification manager.
    
    Args:
        message: Notification message
        type: Notification type
        title: Optional notification title
        duration: Display duration in milliseconds
        position: Display position
        closable: Whether the notification can be closed manually
        auto_close: Whether the notification should close automatically
        icon: Optional icon for the notification
        data: Optional additional data
        
    Returns:
        Created notification
    """
    return get_notification_manager().create_notification(
        message=message,
        type=type,
        title=title,
        duration=duration,
        position=position,
        closable=closable,
        auto_close=auto_close,
        icon=icon,
        data=data
    )
