import uuid
import os
import logging
import threading
import pandas as pd
import numpy as np
from typing import Dict, Any, Optional, List
import json
from datetime import datetime
import time
from pathlib import Path

from .ppo_agent import PPOAgent
from .env import TradingEnvironment

logger = logging.getLogger(__name__)

_training_jobs = {}
_training_lock = threading.Lock()
_auto_training_thread = None
_auto_training_active = False

def start_training(
    symbol: str = "BTC/USDT",
    timeframe: str = "1h",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    initial_balance: float = 10000.0,
    episodes: int = 100,
    background: bool = True
) -> str:
    """
    Start training a reinforcement learning agent.
    
    Args:
        symbol: Trading pair symbol
        timeframe: Timeframe for data
        start_date: Start date for training data
        end_date: End date for training data
        initial_balance: Initial account balance
        episodes: Number of training episodes
        background: Whether to run training in background thread
        
    Returns:
        str: Job ID for the training job
    """
    job_id = str(uuid.uuid4())
    
    logger.info(f"Starting training job {job_id} for {symbol} on {timeframe} timeframe")
    
    job_info = {
        'job_id': job_id,
        'symbol': symbol,
        'timeframe': timeframe,
        'start_date': start_date,
        'end_date': end_date,
        'initial_balance': initial_balance,
        'episodes': episodes,
        'status': 'pending',
        'progress': 0,
        'start_time': datetime.now().isoformat(),
        'metrics': {},
        'model_path': None
    }
    
    with _training_lock:
        _training_jobs[job_id] = job_info
    
    if background:
        thread = threading.Thread(
            target=_run_training_job,
            args=(job_id,),
            daemon=True
        )
        thread.start()
    else:
        _run_training_job(job_id)
    
    return job_id

def _run_training_job(job_id: str) -> None:
    """
    Run a training job in the background.
    
    Args:
        job_id: ID of the job to run
    """
    try:
        with _training_lock:
            job_info = _training_jobs[job_id]
        
        _update_job_status(job_id, 'running', 0)
        
        env = TradingEnvironment(
            symbol=job_info['symbol'],
            timeframe=job_info['timeframe'],
            start_date=job_info['start_date'],
            end_date=job_info['end_date'],
            initial_balance=job_info['initial_balance']
        )
        
        agent = PPOAgent(
            state_dim=env.observation_space.shape[0],
            action_dim=env.action_space.n,
            lr=0.0003
        )
        
        best_reward = -float('inf')
        best_model_path = None
        
        for episode in range(job_info['episodes']):
            state, _ = env.reset()
            done = False
            truncated = False
            total_reward = 0
            
            while not done and not truncated:
                action, log_prob, value = agent.select_action(state)
                step_result = env.step(action)
                
                if len(step_result) == 5:
                    next_state, reward, done, truncated, info = step_result
                else:
                    next_state, reward, done, info = step_result
                    truncated = False
                
                agent.store_transition(state, action, reward, value, log_prob, done)
                state = next_state
                total_reward += reward
            
            progress = int((episode + 1) / job_info['episodes'] * 100)
            
            _, _, last_value = agent.select_action(state)
            
            agent.finish_episode(last_value, done)
            
            update_metrics = agent.update()
            
            agent.add_episode_metrics(total_reward, len(env.portfolio_history))
            
            metrics = {
                'episode': episode + 1,
                'total_reward': float(total_reward),
                'final_portfolio_value': float(env.portfolio_value),
                'best_portfolio_value': float(max(env.portfolio_history)),
                'policy_loss': update_metrics.get('policy_loss', 0),
                'value_loss': update_metrics.get('value_loss', 0)
            }
            
            _update_job_status(job_id, 'running', progress, metrics)
            
            if total_reward > best_reward:
                best_reward = total_reward
                
                models_dir = Path("models")
                models_dir.mkdir(exist_ok=True)
                
                best_model_path = f"models/{job_info['symbol'].replace('/', '_')}_{job_id}.pt"
                agent.save(best_model_path)
                
                with _training_lock:
                    _training_jobs[job_id]['model_path'] = best_model_path
        
        final_metrics = {
            'episodes': job_info['episodes'],
            'best_reward': float(best_reward),
            'training_time': (datetime.now() - datetime.fromisoformat(job_info['start_time'])).total_seconds(),
            'model_path': best_model_path
        }
        
        _update_job_status(job_id, 'completed', 100, final_metrics)
        
    except Exception as e:
        logger.error(f"Error in training job {job_id}: {str(e)}")
        _update_job_status(job_id, 'failed', 0, {'error': str(e)})

def _update_job_status(job_id: str, status: str, progress: int, metrics: Dict[str, Any] = None) -> None:
    """
    Update the status of a training job.
    
    Args:
        job_id: ID of the job to update
        status: New status
        progress: Progress percentage (0-100)
        metrics: Optional metrics to update
    """
    with _training_lock:
        if job_id in _training_jobs:
            _training_jobs[job_id]['status'] = status
            _training_jobs[job_id]['progress'] = progress
            
            if metrics:
                _training_jobs[job_id]['metrics'].update(metrics)
            
            _training_jobs[job_id]['last_updated'] = datetime.now().isoformat()

def get_training_status(job_id: str) -> Dict[str, Any]:
    """
    Get the status of a training job.
    
    Args:
        job_id: Job ID to check
        
    Returns:
        Dict: Job status information
    """
    with _training_lock:
        if job_id in _training_jobs:
            return _training_jobs[job_id].copy()
        
    return {
        'job_id': job_id,
        'status': 'not_found',
        'error': 'Training job not found'
    }

def get_all_training_jobs() -> List[Dict[str, Any]]:
    """
    Get information about all training jobs.
    
    Returns:
        List[Dict]: List of job information dictionaries
    """
    with _training_lock:
        return list(_training_jobs.values())

def start_auto_training(active: bool = True) -> None:
    """
    Start or stop the automatic training system that continuously
    improves trading strategies without user intervention.
    
    Args:
        active: Whether to activate or deactivate auto-training
    """
    global _auto_training_thread, _auto_training_active
    
    if active and (_auto_training_thread is None or not _auto_training_thread.is_alive()):
        _auto_training_active = True
        _auto_training_thread = threading.Thread(
            target=_auto_training_loop,
            daemon=True
        )
        _auto_training_thread.start()
        logger.info("Auto-training system activated")
    elif not active and _auto_training_thread is not None:
        _auto_training_active = False
        logger.info("Auto-training system deactivated")

def _auto_training_loop() -> None:
    """
    Background loop that continuously trains and improves models
    without user intervention.
    """
    symbols = ["BTC/USDT", "ETH/USDT", "XRP/USDT", "SOL/USDT", "ADA/USDT"]
    timeframes = ["15m", "1h", "4h", "1d"]
    
    while _auto_training_active:
        try:
            symbol = np.random.choice(symbols)
            timeframe = np.random.choice(timeframes)
            
            # Start a new training job
            job_id = start_training(
                symbol=symbol,
                timeframe=timeframe,
                episodes=200,
                background=True
            )
            
            logger.info(f"Auto-training started job {job_id} for {symbol} on {timeframe}")
            
            time.sleep(3600)  # 1 hour
            
        except Exception as e:
            logger.error(f"Error in auto-training loop: {str(e)}")
            time.sleep(300)  # 5 minutes

start_auto_training(True)
