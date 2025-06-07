from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
import logging
import os
import json
import asyncio
from datetime import datetime
from typing import List, Dict, Any
import threading
import time

logger = logging.getLogger(__name__)
router = APIRouter()

@router.get("/api/automation/logs")
async def get_automation_logs():
    """
    Get real-time automation logs from log files.
    
    Returns:
        JSON response with recent automation activity logs
    """
    try:
        logs = []
        current_time = datetime.now()
        
        log_files = [
            "/app/autobot.log",  # Main application log
            "/app/logs/scheduler.log",  # Scheduler log
            "/app/logs/worker.log"  # Worker log
        ]
        
        for log_file in log_files:
            try:
                if os.path.exists(log_file):
                    with open(log_file, 'r') as f:
                        lines = f.readlines()[-20:]  # Get last 20 lines
                        
                    for line in lines:
                        if any(keyword in line for keyword in [
                            'autobot.trading.auto_mode_manager',
                            'autobot.scheduler',
                            'autobot.ui.backtest_routes',
                            'autobot.trading.fund_manager',
                            'autobot.ui.ecommerce_routes'
                        ]):
                            timestamp_match = line.split(' - ')[0] if ' - ' in line else current_time.strftime('%Y-%m-%d %H:%M:%S')
                            try:
                                log_time = datetime.strptime(timestamp_match.split(',')[0], '%Y-%m-%d %H:%M:%S').strftime('%H:%M:%S')
                            except:
                                log_time = current_time.strftime('%H:%M:%S')
                            
                            if 'Mode changed' in line:
                                logs.append({
                                    'time': log_time,
                                    'system': 'AUTOMODE',
                                    'message': line.split(' - ')[-1].strip() if ' - ' in line else line.strip(),
                                    'type': 'success'
                                })
                            elif 'optimization' in line.lower():
                                logs.append({
                                    'time': log_time,
                                    'system': 'SCHEDULER',
                                    'message': line.split(' - ')[-1].strip() if ' - ' in line else line.strip(),
                                    'type': 'info'
                                })
                            elif 'fund_manager' in line:
                                logs.append({
                                    'time': log_time,
                                    'system': 'FUND_MANAGER',
                                    'message': line.split(' - ')[-1].strip() if ' - ' in line else line.strip(),
                                    'type': 'success'
                                })
                            elif 'ecommerce' in line:
                                logs.append({
                                    'time': log_time,
                                    'system': 'E-COMMERCE',
                                    'message': line.split(' - ')[-1].strip() if ' - ' in line else line.strip(),
                                    'type': 'info'
                                })
            except Exception as e:
                logger.warning(f"Could not read log file {log_file}: {str(e)}")
        
        logs.sort(key=lambda x: x['time'], reverse=True)
        
        return JSONResponse(content={"logs": logs[:10]})  # Return last 10 logs
        
    except Exception as e:
        logger.error(f"Error fetching automation logs: {str(e)}")
        return JSONResponse(content={"logs": []})

@router.get("/api/automation/status")
async def get_automation_status():
    """
    Get current automation status and active threads.
    
    Returns:
        JSON response with automation status information
    """
    try:
        import threading
        active_threads = [t.name for t in threading.enumerate()]
        
        automation_active = any(
            'scheduler' in thread.lower() or 
            'optimization' in thread.lower() or
            'automode' in thread.lower()
            for thread in active_threads
        )
        
        return JSONResponse(content={
            "automation_active": automation_active,
            "active_threads": active_threads,
            "thread_count": len(active_threads),
            "status": "active" if automation_active else "inactive"
        })
        
    except Exception as e:
        logger.error(f"Error checking automation status: {str(e)}")
        return JSONResponse(content={
            "automation_active": False,
            "active_threads": [],
            "thread_count": 0,
            "status": "error"
        })

active_log_connections: List[WebSocket] = []
log_streaming_active = False
log_stream_thread = None

@router.websocket("/ws/automation/logs")
async def websocket_automation_logs(websocket: WebSocket):
    """WebSocket endpoint for real-time automation log streaming."""
    await websocket.accept()
    active_log_connections.append(websocket)
    
    global log_streaming_active, log_stream_thread
    
    if not log_streaming_active:
        log_streaming_active = True
        log_stream_thread = threading.Thread(target=stream_logs_to_websockets, daemon=True)
        log_stream_thread.start()
    
    try:
        initial_logs = await get_automation_logs()
        await websocket.send_text(initial_logs.body.decode())
        
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        if websocket in active_log_connections:
            active_log_connections.remove(websocket)
        if not active_log_connections:
            log_streaming_active = False
    except Exception as e:
        logger.error(f"WebSocket error: {str(e)}")
        if websocket in active_log_connections:
            active_log_connections.remove(websocket)

def stream_logs_to_websockets():
    """Background thread to stream logs to WebSocket connections."""
    last_log_positions = {}
    
    while log_streaming_active and active_log_connections:
        try:
            new_logs = []
            log_files = [
                "/app/autobot.log",
                "/app/logs/scheduler.log", 
                "/app/logs/worker.log"
            ]
            
            for log_file in log_files:
                if os.path.exists(log_file):
                    try:
                        with open(log_file, 'r') as f:
                            # Get current file size
                            f.seek(0, 2)  # Seek to end
                            current_size = f.tell()
                            
                            last_position = last_log_positions.get(log_file, 0)
                            if current_size > last_position:
                                f.seek(last_position)
                                new_lines = f.readlines()
                                last_log_positions[log_file] = current_size
                                
                                for line in new_lines:
                                    if any(keyword in line for keyword in [
                                        'autobot.trading.auto_mode_manager',
                                        'autobot.scheduler',
                                        'autobot.ui.backtest_routes',
                                        'autobot.trading.fund_manager',
                                        'autobot.ui.ecommerce_routes'
                                    ]):
                                        current_time = datetime.now()
                                        try:
                                            timestamp_match = line.split(' - ')[0] if ' - ' in line else current_time.strftime('%Y-%m-%d %H:%M:%S')
                                            log_time = datetime.strptime(timestamp_match.split(',')[0], '%Y-%m-%d %H:%M:%S').strftime('%H:%M:%S')
                                        except:
                                            log_time = current_time.strftime('%H:%M:%S')
                                        
                                        if 'Mode changed' in line:
                                            new_logs.append({
                                                'time': log_time,
                                                'system': 'AUTOMODE',
                                                'message': line.split(' - ')[-1].strip(),
                                                'type': 'success'
                                            })
                                        elif 'optimization' in line.lower():
                                            new_logs.append({
                                                'time': log_time,
                                                'system': 'SCHEDULER',
                                                'message': line.split(' - ')[-1].strip(),
                                                'type': 'info'
                                            })
                                        elif 'fund_manager' in line:
                                            new_logs.append({
                                                'time': log_time,
                                                'system': 'FUND_MANAGER',
                                                'message': line.split(' - ')[-1].strip(),
                                                'type': 'success'
                                            })
                                        elif 'ecommerce' in line:
                                            new_logs.append({
                                                'time': log_time,
                                                'system': 'E-COMMERCE',
                                                'message': line.split(' - ')[-1].strip(),
                                                'type': 'info'
                                            })
                    except Exception as e:
                        logger.warning(f"Error reading {log_file}: {str(e)}")
            
            if new_logs:
                message = json.dumps({"logs": new_logs})
                disconnected = []
                for websocket in active_log_connections:
                    try:
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        loop.run_until_complete(websocket.send_text(message))
                        loop.close()
                    except:
                        disconnected.append(websocket)
                
                for ws in disconnected:
                    if ws in active_log_connections:
                        active_log_connections.remove(ws)
            
            time.sleep(2)  # Check for new logs every 2 seconds
            
        except Exception as e:
            logger.error(f"Error in log streaming: {str(e)}")
            time.sleep(5)

active_log_connections: List[WebSocket] = []
log_streaming_active = False
log_stream_thread = None

@router.websocket("/ws/automation/logs")
async def websocket_automation_logs(websocket: WebSocket):
    """WebSocket endpoint for real-time automation log streaming."""
    await websocket.accept()
    active_log_connections.append(websocket)
    
    global log_streaming_active, log_stream_thread
    
    if not log_streaming_active:
        log_streaming_active = True
        log_stream_thread = threading.Thread(target=stream_logs_to_websockets, daemon=True)
        log_stream_thread.start()
    
    try:
        initial_logs = await get_automation_logs()
        await websocket.send_text(initial_logs.body.decode())
        
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        if websocket in active_log_connections:
            active_log_connections.remove(websocket)
        if not active_log_connections:
            log_streaming_active = False
    except Exception as e:
        logger.error(f"WebSocket error: {str(e)}")
        if websocket in active_log_connections:
            active_log_connections.remove(websocket)

def stream_logs_to_websockets():
    """Background thread to stream logs to WebSocket connections."""
    last_log_positions = {}
    
    while log_streaming_active and active_log_connections:
        try:
            new_logs = []
            log_files = [
                "/app/logs/scheduler.log",
                "/app/logs/worker.log"
            ]
            
            for log_file in log_files:
                if os.path.exists(log_file):
                    try:
                        with open(log_file, 'r') as f:
                            f.seek(0, 2)
                            current_size = f.tell()
                            
                            last_position = last_log_positions.get(log_file, 0)
                            if current_size > last_position:
                                f.seek(last_position)
                                new_lines = f.readlines()
                                last_log_positions[log_file] = current_size
                                
                                for line in new_lines:
                                    if any(keyword in line for keyword in [
                                        'autobot.trading.auto_mode_manager',
                                        'autobot.scheduler',
                                        'autobot.ui.backtest_routes',
                                        'autobot.trading.fund_manager',
                                        'autobot.ui.ecommerce_routes'
                                    ]):
                                        current_time = datetime.now()
                                        try:
                                            timestamp_match = line.split(' - ')[0] if ' - ' in line else current_time.strftime('%Y-%m-%d %H:%M:%S')
                                            log_time = datetime.strptime(timestamp_match.split(',')[0], '%Y-%m-%d %H:%M:%S').strftime('%H:%M:%S')
                                        except:
                                            log_time = current_time.strftime('%H:%M:%S')
                                        
                                        if 'Mode changed' in line:
                                            new_logs.append({
                                                'time': log_time,
                                                'system': 'AUTOMODE',
                                                'message': line.split(' - ')[-1].strip(),
                                                'type': 'success'
                                            })
                                        elif 'optimization' in line.lower():
                                            new_logs.append({
                                                'time': log_time,
                                                'system': 'SCHEDULER',
                                                'message': line.split(' - ')[-1].strip(),
                                                'type': 'info'
                                            })
                                        elif 'fund_manager' in line:
                                            new_logs.append({
                                                'time': log_time,
                                                'system': 'FUND_MANAGER',
                                                'message': line.split(' - ')[-1].strip(),
                                                'type': 'success'
                                            })
                                        elif 'ecommerce' in line:
                                            new_logs.append({
                                                'time': log_time,
                                                'system': 'E-COMMERCE',
                                                'message': line.split(' - ')[-1].strip(),
                                                'type': 'info'
                                            })
                    except Exception as e:
                        logger.warning(f"Error reading {log_file}: {str(e)}")
            
            if new_logs:
                message = json.dumps({"logs": new_logs})
                disconnected = []
                for websocket in active_log_connections:
                    try:
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        loop.run_until_complete(websocket.send_text(message))
                        loop.close()
                    except:
                        disconnected.append(websocket)
                
                for ws in disconnected:
                    if ws in active_log_connections:
                        active_log_connections.remove(ws)
            
            time.sleep(2)
            
        except Exception as e:
            logger.error(f"Error in log streaming: {str(e)}")
            time.sleep(5)
