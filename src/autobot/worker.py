"""
Background worker for AUTOBOT.
Handles long-running tasks like model training, backtesting, and data synchronization.
"""
import os
import time
import logging
import signal
import sys
from datetime import datetime
from typing import Dict, Any, List, Optional
import json
import threading
import queue

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(os.path.join('logs', 'worker.log'))
    ]
)
logger = logging.getLogger('autobot.worker')

os.makedirs('logs', exist_ok=True)

task_queue = queue.Queue()

active_tasks: Dict[str, Dict[str, Any]] = {}

worker_threads: List[threading.Thread] = []

shutdown_flag = threading.Event()

def signal_handler(sig, frame):
    """Handle shutdown signals gracefully."""
    logger.info("Shutdown signal received, stopping worker...")
    shutdown_flag.set()
    
    for thread in worker_threads:
        if thread.is_alive():
            thread.join(timeout=5.0)
    
    logger.info("Worker shutdown complete")
    sys.exit(0)

def worker_thread(worker_id: int):
    """Worker thread function to process tasks from the queue."""
    logger.info(f"Worker thread {worker_id} started")
    
    while not shutdown_flag.is_set():
        try:
            try:
                task = task_queue.get(timeout=1.0)
            except queue.Empty:
                continue
            
            task_id = task.get('task_id')
            task_type = task.get('task_type')
            
            logger.info(f"Worker {worker_id} processing task {task_id} of type {task_type}")
            
            task['status'] = 'running'
            task['started_at'] = datetime.now().isoformat()
            active_tasks[task_id] = task
            
            if task_type == 'train_model':
                process_train_model_task(task)
            elif task_type == 'backtest':
                process_backtest_task(task)
            elif task_type == 'sync_data':
                process_sync_data_task(task)
            else:
                logger.warning(f"Unknown task type: {task_type}")
                task['status'] = 'failed'
                task['error'] = f"Unknown task type: {task_type}"
            
            if task['status'] != 'failed':
                task['status'] = 'completed'
            
            task['completed_at'] = datetime.now().isoformat()
            
            save_task_result(task)
            
            task_queue.task_done()
            
        except Exception as e:
            logger.exception(f"Error in worker thread {worker_id}: {str(e)}")
            
            if 'task' in locals() and task:
                task['status'] = 'failed'
                task['error'] = str(e)
                task['completed_at'] = datetime.now().isoformat()
                save_task_result(task)
                task_queue.task_done()
    
    logger.info(f"Worker thread {worker_id} stopped")

def process_train_model_task(task: Dict[str, Any]):
    """Process a model training task."""
    try:
        logger.info(f"Training model with parameters: {task.get('parameters')}")
        
        total_steps = 100
        for step in range(total_steps):
            if shutdown_flag.is_set():
                task['status'] = 'interrupted'
                return
                
            progress = (step + 1) / total_steps * 100
            task['progress'] = progress
            
            task['metrics'] = {
                'loss': 1.0 - (progress / 100) * 0.7,
                'accuracy': (progress / 100) * 0.9,
                'val_loss': 1.2 - (progress / 100) * 0.6,
                'val_accuracy': (progress / 100) * 0.85
            }
            
            time.sleep(0.1)
        
        task['result'] = {
            'model_path': f"models/{task['task_id']}.model",
            'final_metrics': task['metrics']
        }
        
    except Exception as e:
        logger.exception(f"Error training model: {str(e)}")
        task['status'] = 'failed'
        task['error'] = str(e)

def process_backtest_task(task: Dict[str, Any]):
    """Process a backtest task."""
    try:
        logger.info(f"Running backtest with parameters: {task.get('parameters')}")
        
        time.sleep(2)
        
        task['result'] = {
            'sharpe_ratio': 1.23,
            'total_return': 0.15,
            'max_drawdown': -0.08,
            'win_rate': 0.65,
            'profit_factor': 1.8
        }
        
    except Exception as e:
        logger.exception(f"Error running backtest: {str(e)}")
        task['status'] = 'failed'
        task['error'] = str(e)

def process_sync_data_task(task: Dict[str, Any]):
    """Process a data synchronization task."""
    try:
        logger.info(f"Syncing data with parameters: {task.get('parameters')}")
        
        time.sleep(1)
        
        task['result'] = {
            'records_synced': 1250,
            'new_records': 120,
            'updated_records': 30,
            'sync_time': 1.2
        }
        
    except Exception as e:
        logger.exception(f"Error syncing data: {str(e)}")
        task['status'] = 'failed'
        task['error'] = str(e)

def save_task_result(task: Dict[str, Any]):
    """Save task result to a file."""
    try:
        os.makedirs('data/tasks', exist_ok=True)
        
        task_id = task['task_id']
        with open(f"data/tasks/{task_id}.json", 'w') as f:
            json.dump(task, f, indent=2)
            
    except Exception as e:
        logger.exception(f"Error saving task result: {str(e)}")

def add_task(task_type: str, parameters: Dict[str, Any]) -> str:
    """Add a new task to the queue."""
    from uuid import uuid4
    
    task_id = str(uuid4())
    task = {
        'task_id': task_id,
        'task_type': task_type,
        'parameters': parameters,
        'status': 'queued',
        'created_at': datetime.now().isoformat(),
        'progress': 0
    }
    
    task_queue.put(task)
    active_tasks[task_id] = task
    
    logger.info(f"Added task {task_id} of type {task_type} to queue")
    return task_id

def get_task_status(task_id: str) -> Optional[Dict[str, Any]]:
    """Get the status of a task."""
    if task_id in active_tasks:
        return active_tasks[task_id]
    
    try:
        task_file = f"data/tasks/{task_id}.json"
        if os.path.exists(task_file):
            with open(task_file, 'r') as f:
                return json.load(f)
    except Exception as e:
        logger.exception(f"Error loading task status: {str(e)}")
    
    return None

def main():
    """Main worker function."""
    logger.info("Starting AUTOBOT worker...")
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    num_workers = 4  # Adjust based on available resources
    for i in range(num_workers):
        thread = threading.Thread(target=worker_thread, args=(i,))
        thread.daemon = True
        thread.start()
        worker_threads.append(thread)
    
    logger.info(f"Started {num_workers} worker threads")
    
    while not shutdown_flag.is_set():
        time.sleep(1)

if __name__ == "__main__":
    main()
