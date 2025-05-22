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

if __name__ == "__main__":
    main()

orchestration_tasks = {}

def add_scheduled_task(task_id, task_func, interval_minutes=60, **kwargs):
    """
    Ajoute une tâche planifiée à exécuter périodiquement pour l'orchestration UI.
    
    Args:
        task_id (str): Identifiant unique de la tâche
        task_func (callable): Fonction à exécuter
        interval_minutes (int): Intervalle en minutes entre les exécutions
        **kwargs: Arguments supplémentaires à passer à la fonction
    
    Returns:
        str: L'identifiant de la tâche
    """
    next_run = datetime.now() + timedelta(minutes=interval_minutes)
    
    orchestration_tasks[task_id] = {
        "func": task_func,
        "interval": timedelta(minutes=interval_minutes),
        "next_run": next_run,
        "last_run": None,
        "kwargs": kwargs,
        "enabled": True
    }
    
    logger.info(f"Tâche d'orchestration planifiée ajoutée: {task_id}, prochaine exécution: {next_run}")
    return task_id

def remove_scheduled_task(task_id):
    """
    Supprime une tâche planifiée de l'orchestration UI.
    
    Args:
        task_id (str): Identifiant unique de la tâche
    
    Returns:
        bool: True si la tâche a été supprimée, False sinon
    """
    if task_id in orchestration_tasks:
        del orchestration_tasks[task_id]
        logger.info(f"Tâche d'orchestration planifiée supprimée: {task_id}")
        return True
    return False

def run_scheduled_tasks():
    """
    Exécute les tâches planifiées de l'orchestration UI dont l'heure d'exécution est arrivée.
    
    Returns:
        list: Liste des identifiants des tâches exécutées
    """
    now = datetime.now()
    executed_tasks = []
    
    for task_id, task in list(orchestration_tasks.items()):
        if not task["enabled"]:
            continue
            
        if now >= task["next_run"]:
            logger.info(f"Exécution de la tâche d'orchestration planifiée: {task_id}")
            
            try:
                task["func"](**task["kwargs"])
                task["last_run"] = now
                task["next_run"] = now + task["interval"]
                logger.info(f"Tâche {task_id} exécutée avec succès, prochaine exécution: {task['next_run']}")
                executed_tasks.append(task_id)
            except Exception as e:
                logger.error(f"Erreur lors de l'exécution de la tâche {task_id}: {str(e)}")
    
    return executed_tasks

def enable_scheduled_task(task_id, enabled=True):
    """
    Active ou désactive une tâche planifiée de l'orchestration UI.
    
    Args:
        task_id (str): Identifiant unique de la tâche
        enabled (bool): True pour activer, False pour désactiver
    
    Returns:
        bool: True si l'état a été modifié, False sinon
    """
    if task_id in orchestration_tasks:
        orchestration_tasks[task_id]["enabled"] = enabled
        status = "activée" if enabled else "désactivée"
        logger.info(f"Tâche d'orchestration {task_id} {status}")
        return True
    return False

def get_scheduled_task(task_id):
    """
    Récupère les informations d'une tâche planifiée de l'orchestration UI.
    
    Args:
        task_id (str): Identifiant unique de la tâche
    
    Returns:
        dict: Informations sur la tâche ou None si la tâche n'existe pas
    """
    if task_id in orchestration_tasks:
        task = orchestration_tasks[task_id].copy()
        task.pop("func", None)
        return task
    return None

def get_all_scheduled_tasks():
    """
    Récupère la liste de toutes les tâches planifiées de l'orchestration UI.
    
    Returns:
        dict: Dictionnaire des tâches planifiées (sans les fonctions)
    """
    tasks = {}
    for task_id, task_data in orchestration_tasks.items():
        task_info = task_data.copy()
        task_info.pop("func", None)
        tasks[task_id] = task_info
    
    return tasks

def schedule_continuous_backtest(strategy, symbol, timeframe, interval_minutes=60):
    """
    Planifie un backtest continu pour une stratégie donnée.
    
    Args:
        strategy (str): Nom de la stratégie
        symbol (str): Symbole de trading
        timeframe (str): Timeframe pour le backtest
        interval_minutes (int): Intervalle en minutes entre les exécutions
    
    Returns:
        str: L'identifiant de la tâche
    """
    from .worker import add_task
    
    def run_backtest():
        task_id = add_task('backtest', {
            'strategy': strategy,
            'symbol': symbol,
            'timeframe': timeframe,
            'continuous': True
        })
        logger.info(f"Backtest continu démarré pour {strategy} sur {symbol} ({timeframe}), task_id: {task_id}")
        return task_id
    
    task_id = f"continuous_backtest_{strategy}_{symbol}_{timeframe}_{int(time.time())}"
    return add_scheduled_task(task_id, run_backtest, interval_minutes)

def schedule_ghosting_rotation(max_instances, evasion_mode, interval_minutes=120):
    """
    Planifie la rotation des instances de ghosting.
    
    Args:
        max_instances (int): Nombre maximum d'instances
        evasion_mode (str): Mode d'évasion
        interval_minutes (int): Intervalle en minutes entre les rotations
    
    Returns:
        str: L'identifiant de la tâche
    """
    from .trading.ghosting_manager import rotate_instances
    
    def run_rotation():
        return rotate_instances(max_instances, evasion_mode)
    
    task_id = f"ghosting_rotation_{evasion_mode}_{int(time.time())}"
    return add_scheduled_task(task_id, run_rotation, interval_minutes)
