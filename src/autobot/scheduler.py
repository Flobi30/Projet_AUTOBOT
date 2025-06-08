"""
Scheduler for AUTOBOT.
Handles scheduled tasks like periodic data updates, model retraining, and system maintenance.
"""
import os
import time
import logging
import signal
import sys
from datetime import datetime, timedelta
import json
import threading
from typing import Dict, Any, List, Callable

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(os.path.join('logs', 'scheduler.log'))
    ]
)
logger = logging.getLogger('autobot.scheduler')

os.makedirs('logs', exist_ok=True)

scheduled_tasks: List[Dict[str, Any]] = []

shutdown_flag = threading.Event()

def signal_handler(sig, frame):
    """Handle shutdown signals gracefully."""
    logger.info("Shutdown signal received, stopping scheduler...")
    shutdown_flag.set()
    logger.info("Scheduler shutdown complete")
    sys.exit(0)

def schedule_task(name: str, interval_seconds: int, task_func: Callable, enabled: bool = True):
    """Schedule a task to run at regular intervals."""
    task = {
        'name': name,
        'interval': interval_seconds,
        'function': task_func,
        'last_run': None,
        'next_run': datetime.now(),
        'enabled': enabled
    }
    
    scheduled_tasks.append(task)
    logger.info(f"Scheduled task '{name}' to run every {interval_seconds} seconds")

def update_market_data():
    """Update market data from exchanges."""
    logger.info("Updating market data...")
    
    try:
        
        from .worker import add_task
        task_id = add_task('sync_data', {
            'sources': ['binance', 'coinbase', 'kraken'],
            'symbols': ['BTC/USDT', 'ETH/USDT', 'SOL/USDT'],
            'timeframes': ['1m', '5m', '15m', '1h', '4h', '1d']
        })
        
        logger.info(f"Created market data update task with ID: {task_id}")
        
    except Exception as e:
        logger.exception(f"Error updating market data: {str(e)}")

def retrain_models():
    """Retrain machine learning models with latest data."""
    logger.info("Retraining models...")
    
    try:
        
        from .worker import add_task
        task_id = add_task('train_model', {
            'model_type': 'ppo',
            'symbols': ['BTC/USDT'],
            'timeframe': '1h',
            'lookback_days': 30,
            'epochs': 100
        })
        
        logger.info(f"Created model retraining task with ID: {task_id}")
        
    except Exception as e:
        logger.exception(f"Error retraining models: {str(e)}")

def run_system_maintenance():
    """Run system maintenance tasks."""
    logger.info("Running system maintenance...")
    
    try:
        log_dir = 'logs'
        if os.path.exists(log_dir):
            current_time = datetime.now()
            for filename in os.listdir(log_dir):
                file_path = os.path.join(log_dir, filename)
                if os.path.isfile(file_path):
                    file_modified = datetime.fromtimestamp(os.path.getmtime(file_path))
                    if current_time - file_modified > timedelta(days=7):
                        os.remove(file_path)
                        logger.info(f"Removed old log file: {filename}")
        
        tasks_dir = 'data/tasks'
        if os.path.exists(tasks_dir):
            current_time = datetime.now()
            for filename in os.listdir(tasks_dir):
                if not filename.endswith('.json'):
                    continue
                    
                file_path = os.path.join(tasks_dir, filename)
                if os.path.isfile(file_path):
                    file_modified = datetime.fromtimestamp(os.path.getmtime(file_path))
                    if current_time - file_modified > timedelta(days=30):
                        os.remove(file_path)
                        logger.info(f"Removed old task result: {filename}")
        
        system_status = {
            'last_maintenance': datetime.now().isoformat(),
            'status': 'healthy',
            'uptime': get_uptime(),
            'disk_usage': get_disk_usage(),
            'memory_usage': get_memory_usage(),
            'cpu_usage': get_cpu_usage()
        }
        
        os.makedirs('data/system', exist_ok=True)
        with open('data/system/status.json', 'w') as f:
            json.dump(system_status, f, indent=2)
            
        logger.info("System maintenance completed")
        
    except Exception as e:
        logger.exception(f"Error during system maintenance: {str(e)}")

def get_uptime():
    """Get system uptime."""
    try:
        with open('/proc/uptime', 'r') as f:
            uptime_seconds = float(f.readline().split()[0])
        return uptime_seconds
    except:
        return 0

def get_disk_usage():
    """Get disk usage information."""
    try:
        total, used, free = 0, 0, 0
        if os.name == 'posix':
            st = os.statvfs('/')
            total = st.f_blocks * st.f_frsize
            free = st.f_bavail * st.f_frsize
            used = total - free
        
        return {
            'total': total,
            'used': used,
            'free': free,
            'percent': (used / total * 100) if total > 0 else 0
        }
    except:
        return {'total': 0, 'used': 0, 'free': 0, 'percent': 0}

def get_memory_usage():
    """Get memory usage information."""
    try:
        import psutil
        mem = psutil.virtual_memory()
        return {
            'total': mem.total,
            'available': mem.available,
            'used': mem.used,
            'percent': mem.percent
        }
    except:
        return {'total': 0, 'available': 0, 'used': 0, 'percent': 0}

def get_cpu_usage():
    """Get CPU usage information."""
    try:
        import psutil
        return psutil.cpu_percent(interval=1)
    except:
        return 0

def main():
    """Main scheduler function."""
    logger.info("Starting AUTOBOT scheduler...")
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    schedule_task("Market Data Update", 300, update_market_data)  # Every 5 minutes
    schedule_task("Model Retraining", 86400, retrain_models)  # Once a day
    schedule_task("System Maintenance", 3600, run_system_maintenance)  # Once an hour
    
    while not shutdown_flag.is_set():
        current_time = datetime.now()
        
        for task in scheduled_tasks:
            if not task['enabled']:
                continue
                
            if task['next_run'] <= current_time:
                logger.info(f"Running scheduled task: {task['name']}")
                
                try:
                    task['function']()
                    task['last_run'] = current_time
                except Exception as e:
                    logger.exception(f"Error running task {task['name']}: {str(e)}")
                
                task['next_run'] = current_time + timedelta(seconds=task['interval'])
                logger.info(f"Next run of {task['name']} scheduled for {task['next_run']}")
        
        time.sleep(1)

def start_scheduler():
    """Start the scheduler in a background thread."""
    logger.info("Starting AUTOBOT scheduler...")
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    schedule_task("Market Data Update", 300, update_market_data)  # Every 5 minutes
    schedule_task("Model Retraining", 86400, retrain_models)  # Once a day
    schedule_task("System Maintenance", 3600, run_system_maintenance)  # Once an hour
    
    while not shutdown_flag.is_set():
        current_time = datetime.now()
        
        for task in scheduled_tasks:
            if not task['enabled']:
                continue
                
            if task['next_run'] <= current_time:
                logger.info(f"Running scheduled task: {task['name']}")
                
                try:
                    task['function']()
                    task['last_run'] = current_time
                except Exception as e:
                    logger.exception(f"Error running task {task['name']}: {str(e)}")
                
                task['next_run'] = current_time + timedelta(seconds=task['interval'])
                logger.info(f"Next run of {task['name']} scheduled for {task['next_run']}")
        
        time.sleep(1)

def shutdown_scheduler():
    """Shutdown the scheduler gracefully."""
    logger.info("Shutting down scheduler...")
    shutdown_flag.set()

if __name__ == "__main__":
    main()
