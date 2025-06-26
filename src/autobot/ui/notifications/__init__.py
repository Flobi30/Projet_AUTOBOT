"""
Notification system for AUTOBOT UI.
Provides a flexible system for displaying notifications to users.
"""

from .notification_manager import (
    NotificationManager,
    Notification,
    NotificationType,
    NotificationPosition,
    create_notification,
    get_notification_manager
)

__all__ = [
    'NotificationManager',
    'Notification',
    'NotificationType',
    'NotificationPosition',
    'create_notification',
    'get_notification_manager'
]
