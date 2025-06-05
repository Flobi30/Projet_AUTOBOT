"""
AUTOBOT Chat WebSocket Routes with Custom SuperAGI Implementation

This module implements the WebSocket routes for the chat interface that communicates
with the AutobotMaster agent using the custom SuperAGI implementation.
"""

import json
import logging
from typing import Dict, List, Any
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
import asyncio

from ..agents.custom_superagi.master_agent import create_autobot_master_agent


logger = logging.getLogger(__name__)

router = APIRouter()

active_connections: Dict[str, List[WebSocket]] = {}
autobot_master = None

@router.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket):
    """WebSocket endpoint for chat communication."""
    await websocket.accept()
    
    user_id = "AUTOBOT"
    if user_id not in active_connections:
        active_connections[user_id] = []
    active_connections[user_id].append(websocket)
    
    global autobot_master
    if autobot_master is None:
        autobot_master = create_autobot_master_agent()
    
    try:
        await websocket.send_json({
            "message": "Bonjour, je suis AutobotMaster. Comment puis-je vous aider?"
        })
        
        while True:
            data = await websocket.receive_text()
            try:
                message_data = json.loads(data)
                user_message = message_data.get("message", "")
                
                if user_message:
                    response = autobot_master.process_message(user_message)
                    
                    await websocket.send_json({
                        "message": response
                    })
                    
                    logger.info(f"Processed message from user {user_id}: {user_message[:50]}...")
            except json.JSONDecodeError:
                logger.error(f"Invalid JSON received: {data}")
                await websocket.send_json({
                    "message": "Désolé, j'ai rencontré une erreur en traitant votre message."
                })
            except Exception as e:
                logger.error(f"Error processing message: {str(e)}")
                await websocket.send_json({
                    "message": f"Désolé, une erreur s'est produite: {str(e)}"
                })
    
    except WebSocketDisconnect:
        if user_id in active_connections:
            active_connections[user_id].remove(websocket)
            if not active_connections[user_id]:
                del active_connections[user_id]
        
        logger.info(f"WebSocket disconnected for user {user_id}")
    
    except Exception as e:
        logger.error(f"WebSocket error: {str(e)}")
