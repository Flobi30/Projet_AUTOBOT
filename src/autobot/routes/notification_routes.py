"""
Notification routes for AUTOBOT.
"""
from fastapi import APIRouter, Response, Request, HTTPException, status, Depends
from typing import Dict, List, Any, Optional
from sse_starlette.sse import EventSourceResponse
import asyncio
import json
import logging
from datetime import datetime

from ..ui.notifications import (
    get_notification_manager,
    NotificationType,
    NotificationPosition,
    create_notification
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/notifications", tags=["Notifications"])

ACTIVE_CONNECTIONS = set()

@router.get("", summary="Get all active notifications")
async def get_notifications() -> List[Dict[str, Any]]:
    """
    Get all active notifications.
    
    Returns:
        List of active notifications
    """
    manager = get_notification_manager()
    notifications = manager.get_active_notifications()
    return [notification.to_dict() for notification in notifications]

@router.get("/history", summary="Get notification history")
async def get_notification_history(limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """
    Get notification history.
    
    Args:
        limit: Optional limit on number of notifications to return
        
    Returns:
        List of historical notifications
    """
    manager = get_notification_manager()
    notifications = manager.get_notification_history(limit)
    return [notification.to_dict() for notification in notifications]

@router.post("", summary="Create a notification", status_code=status.HTTP_201_CREATED)
async def create_notification_endpoint(
    message: str,
    type: NotificationType = NotificationType.INFO,
    title: Optional[str] = None,
    duration: int = 5000,
    position: NotificationPosition = NotificationPosition.TOP_RIGHT,
    closable: bool = True,
    auto_close: bool = True,
    icon: Optional[str] = None,
    data: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
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
    notification = create_notification(
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
    
    await notify_clients(notification.to_dict())
    
    return notification.to_dict()

@router.get("/{notification_id}", summary="Get a notification by ID")
async def get_notification(notification_id: str) -> Dict[str, Any]:
    """
    Get a notification by ID.
    
    Args:
        notification_id: Notification ID
        
    Returns:
        Notification if found
    """
    manager = get_notification_manager()
    notification = manager.get_notification(notification_id)
    
    if not notification:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Notification with ID {notification_id} not found"
        )
    
    return notification.to_dict()

@router.post("/{notification_id}/close", summary="Close a notification")
async def close_notification(notification_id: str) -> Dict[str, Any]:
    """
    Close a notification by ID.
    
    Args:
        notification_id: Notification ID
        
    Returns:
        Success message
    """
    manager = get_notification_manager()
    success = manager.remove_notification(notification_id)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Notification with ID {notification_id} not found"
        )
    
    return {"success": True, "message": f"Notification {notification_id} closed"}

@router.post("/{notification_id}/read", summary="Mark a notification as read")
async def mark_notification_as_read(notification_id: str) -> Dict[str, Any]:
    """
    Mark a notification as read.
    
    Args:
        notification_id: Notification ID
        
    Returns:
        Success message
    """
    manager = get_notification_manager()
    success = manager.mark_as_read(notification_id)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Notification with ID {notification_id} not found"
        )
    
    return {"success": True, "message": f"Notification {notification_id} marked as read"}

@router.post("/read-all", summary="Mark all notifications as read")
async def mark_all_notifications_as_read() -> Dict[str, Any]:
    """
    Mark all notifications as read.
    
    Returns:
        Success message
    """
    manager = get_notification_manager()
    manager.mark_all_as_read()
    
    return {"success": True, "message": "All notifications marked as read"}

@router.delete("", summary="Clear all notifications")
async def clear_notifications() -> Dict[str, Any]:
    """
    Clear all active notifications.
    
    Returns:
        Success message
    """
    manager = get_notification_manager()
    manager.clear_notifications()
    
    return {"success": True, "message": "All notifications cleared"}

@router.get("/stream", summary="Stream notifications")
async def stream_notifications(request: Request) -> EventSourceResponse:
    """
    Stream notifications using Server-Sent Events.
    
    Args:
        request: FastAPI request
        
    Returns:
        EventSourceResponse for streaming notifications
    """
    async def event_generator():
        connection_id = id(request)
        queue = asyncio.Queue()
        
        ACTIVE_CONNECTIONS.add((connection_id, queue))
        
        try:
            yield {
                "event": "ping",
                "data": json.dumps({"time": datetime.now().isoformat()})
            }
            
            while True:
                if await request.is_disconnected():
                    break
                
                try:
                    notification = await asyncio.wait_for(queue.get(), timeout=30)
                    yield {
                        "event": "notification",
                        "data": json.dumps(notification)
                    }
                except asyncio.TimeoutError:
                    yield {
                        "event": "ping",
                        "data": json.dumps({"time": datetime.now().isoformat()})
                    }
        finally:
            ACTIVE_CONNECTIONS.discard((connection_id, queue))
    
    return EventSourceResponse(event_generator())

async def notify_clients(notification: Dict[str, Any]) -> None:
    """
    Notify all connected clients about a new notification.
    
    Args:
        notification: Notification to send
    """
    for _, queue in ACTIVE_CONNECTIONS:
        await queue.put(notification)
