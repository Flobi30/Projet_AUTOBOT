"""
Accelerated learning module for AUTOBOT RL system.

This module provides utilities to accelerate the reinforcement learning process
through advanced techniques like experience replay, prioritized sampling,
and distributed training.
"""

import os
import time
import threading
import logging
import numpy as np
import random
from typing import Dict, List, Any, Optional, Tuple, Callable
from collections import deque
import json
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

@dataclass
class Experience:
    """A single experience tuple for reinforcement learning."""
    state: np.ndarray
    action: int
    reward: float
    next_state: np.ndarray
    done: bool
    info: Dict[str, Any] = field(default_factory=dict)
    priority: float = 1.0
    timestamp: float = field(default_factory=time.time)

class ExperienceBuffer:
    """
    Experience replay buffer with prioritized sampling.
    
    This buffer stores experiences and allows for prioritized sampling
    to accelerate learning by focusing on important transitions.
    """
    
    def __init__(
        self,
        capacity: int = 100000,
        alpha: float = 0.6,
        beta: float = 0.4,
        beta_increment: float = 0.001,
        epsilon: float = 0.01,
        visible_interface: bool = False
    ):
        """
        Initialize the experience buffer.
        
        Args:
            capacity: Maximum number of experiences to store
            alpha: How much prioritization to use (0 = none, 1 = full)
            beta: Importance sampling correction factor
            beta_increment: How much to increase beta over time
            epsilon: Small constant to add to priorities to ensure non-zero
            visible_interface: Whether to show buffer messages in the interface
        """
        self.capacity = capacity
        self.alpha = alpha
        self.beta = beta
        self.beta_increment = beta_increment
        self.epsilon = epsilon
        self.visible_interface = visible_interface
        
        self.buffer = []
        self.priorities = np.zeros(capacity, dtype=np.float32)
        self.position = 0
        self.size = 0
        
        self._lock = threading.Lock()
        
        if self.visible_interface:
            logger.info(f"Created experience buffer with capacity {capacity}")
        else:
            logger.debug(f"Created experience buffer with capacity {capacity}")
    
    def add(self, experience: Experience) -> None:
        """
        Add an experience to the buffer.
        
        Args:
            experience: Experience to add
        """
        with self._lock:
            if len(self.buffer) < self.capacity:
                self.buffer.append(experience)
            else:
                self.buffer[self.position] = experience
            
            max_priority = np.max(self.priorities[:self.size]) if self.size > 0 else 1.0
            self.priorities[self.position] = max_priority
            
            self.position = (self.position + 1) % self.capacity
            self.size = min(self.size + 1, self.capacity)
    
    def sample(self, batch_size: int) -> Tuple[List[Experience], List[int], np.ndarray]:
        """
        Sample a batch of experiences from the buffer.
        
        Args:
            batch_size: Number of experiences to sample
            
        Returns:
            Tuple: (experiences, indices, weights)
        """
        with self._lock:
            if self.size < batch_size:
                batch_size = self.size
            
            priorities = self.priorities[:self.size] ** self.alpha
            probabilities = priorities / np.sum(priorities)
            
            indices = np.random.choice(self.size, batch_size, replace=False, p=probabilities)
            
            weights = (self.size * probabilities[indices]) ** -self.beta
            weights = weights / np.max(weights)
            
            self.beta = min(1.0, self.beta + self.beta_increment)
            
            experiences = [self.buffer[idx] for idx in indices]
            
            return experiences, indices, weights
    
    def update_priorities(self, indices: List[int], priorities: List[float]) -> None:
        """
        Update priorities for experiences.
        
        Args:
            indices: Indices of experiences to update
            priorities: New priorities for experiences
        """
        with self._lock:
            for idx, priority in zip(indices, priorities):
                self.priorities[idx] = priority + self.epsilon
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get statistics about the buffer.
        
        Returns:
            Dict: Buffer statistics
        """
        with self._lock:
            return {
                "size": self.size,
                "capacity": self.capacity,
                "fill_percentage": (self.size / self.capacity) * 100 if self.capacity > 0 else 0,
                "beta": self.beta,
                "mean_priority": np.mean(self.priorities[:self.size]) if self.size > 0 else 0,
                "max_priority": np.max(self.priorities[:self.size]) if self.size > 0 else 0,
                "min_priority": np.min(self.priorities[:self.size]) if self.size > 0 else 0
            }
    
    def save(self, path: str) -> None:
        """
        Save the buffer to disk.
        
        Args:
            path: Path to save buffer to
        """
        with self._lock:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            
            serialized_buffer = []
            for exp in self.buffer[:self.size]:
                serialized_exp = {
                    "state": exp.state.tolist() if isinstance(exp.state, np.ndarray) else exp.state,
                    "action": exp.action,
                    "reward": exp.reward,
                    "next_state": exp.next_state.tolist() if isinstance(exp.next_state, np.ndarray) else exp.next_state,
                    "done": exp.done,
                    "info": exp.info,
                    "priority": exp.priority,
                    "timestamp": exp.timestamp
                }
                serialized_buffer.append(serialized_exp)
            
            data = {
                "buffer": serialized_buffer,
                "priorities": self.priorities[:self.size].tolist(),
                "position": self.position,
                "size": self.size,
                "alpha": self.alpha,
                "beta": self.beta,
                "beta_increment": self.beta_increment,
                "epsilon": self.epsilon
            }
            
            with open(path, "w") as f:
                json.dump(data, f)
            
            if self.visible_interface:
                logger.info(f"Saved experience buffer to {path}")
            else:
                logger.debug(f"Saved experience buffer to {path}")
    
    def load(self, path: str) -> bool:
        """
        Load the buffer from disk.
        
        Args:
            path: Path to load buffer from
            
        Returns:
            bool: True if successful, False otherwise
        """
        with self._lock:
            if not os.path.exists(path):
                if self.visible_interface:
                    logger.warning(f"Buffer file {path} does not exist")
                else:
                    logger.debug(f"Buffer file {path} does not exist")
                return False
            
            try:
                with open(path, "r") as f:
                    data = json.load(f)
                
                self.alpha = data.get("alpha", self.alpha)
                self.beta = data.get("beta", self.beta)
                self.beta_increment = data.get("beta_increment", self.beta_increment)
                self.epsilon = data.get("epsilon", self.epsilon)
                self.position = data.get("position", 0)
                self.size = data.get("size", 0)
                
                priorities = data.get("priorities", [])
                self.priorities[:len(priorities)] = np.array(priorities, dtype=np.float32)
                
                serialized_buffer = data.get("buffer", [])
                self.buffer = []
                
                for serialized_exp in serialized_buffer:
                    state = np.array(serialized_exp["state"]) if isinstance(serialized_exp["state"], list) else serialized_exp["state"]
                    next_state = np.array(serialized_exp["next_state"]) if isinstance(serialized_exp["next_state"], list) else serialized_exp["next_state"]
                    
                    exp = Experience(
                        state=state,
                        action=serialized_exp["action"],
                        reward=serialized_exp["reward"],
                        next_state=next_state,
                        done=serialized_exp["done"],
                        info=serialized_exp["info"],
                        priority=serialized_exp["priority"],
                        timestamp=serialized_exp["timestamp"]
                    )
                    
                    self.buffer.append(exp)
                
                if self.visible_interface:
                    logger.info(f"Loaded experience buffer from {path} with {self.size} experiences")
                else:
                    logger.debug(f"Loaded experience buffer from {path} with {self.size} experiences")
                
                return True
                
            except Exception as e:
                if self.visible_interface:
                    logger.error(f"Failed to load buffer from {path}: {str(e)}")
                else:
                    logger.debug(f"Failed to load buffer from {path}: {str(e)}")
                
                return False

class AcceleratedLearning:
    """
    Accelerated learning system for reinforcement learning.
    
    This class provides utilities to accelerate the reinforcement learning process
    through advanced techniques like experience replay, prioritized sampling,
    and distributed training.
    """
    
    def __init__(
        self,
        buffer_capacity: int = 100000,
        batch_size: int = 64,
        learning_rate: float = 0.001,
        discount_factor: float = 0.99,
        target_update_frequency: int = 1000,
        visible_interface: bool = False
    ):
        """
        Initialize the accelerated learning system.
        
        Args:
            buffer_capacity: Maximum number of experiences to store
            batch_size: Number of experiences to sample for each update
            learning_rate: Learning rate for the optimizer
            discount_factor: Discount factor for future rewards
            target_update_frequency: How often to update target network
            visible_interface: Whether to show learning messages in the interface
        """
        self.buffer_capacity = buffer_capacity
        self.batch_size = batch_size
        self.learning_rate = learning_rate
        self.discount_factor = discount_factor
        self.target_update_frequency = target_update_frequency
        self.visible_interface = visible_interface
        
        self.experience_buffer = ExperienceBuffer(
            capacity=buffer_capacity,
            visible_interface=visible_interface
        )
        
        self.update_count = 0
        self.training_steps = 0
        self.episode_count = 0
        self.total_rewards = []
        
        self._lock = threading.Lock()
        
        if self.visible_interface:
            logger.info("Initialized accelerated learning system")
        else:
            logger.debug("Initialized accelerated learning system")
    
    def add_experience(self, experience: Experience) -> None:
        """
        Add an experience to the buffer.
        
        Args:
            experience: Experience to add
        """
        self.experience_buffer.add(experience)
    
    def update(self, model_update_fn: Callable[[List[Experience], np.ndarray], Tuple[List[float], float]]) -> Optional[float]:
        """
        Update the model using experiences from the buffer.
        
        Args:
            model_update_fn: Function to update the model
                Takes (experiences, weights) and returns (td_errors, loss)
                
        Returns:
            float: Loss value or None if buffer is too small
        """
        with self._lock:
            if self.experience_buffer.size < self.batch_size:
                return None
            
            experiences, indices, weights = self.experience_buffer.sample(self.batch_size)
            
            td_errors, loss = model_update_fn(experiences, weights)
            
            self.experience_buffer.update_priorities(indices, np.abs(td_errors))
            
            self.update_count += 1
            self.training_steps += 1
            
            if self.visible_interface and self.update_count % 100 == 0:
                logger.info(f"Training step {self.training_steps}, loss: {loss:.6f}")
            elif self.update_count % 1000 == 0:
                logger.debug(f"Training step {self.training_steps}, loss: {loss:.6f}")
            
            return loss
    
    def end_episode(self, total_reward: float) -> None:
        """
        Signal the end of an episode.
        
        Args:
            total_reward: Total reward for the episode
        """
        with self._lock:
            self.episode_count += 1
            self.total_rewards.append(total_reward)
            
            if len(self.total_rewards) > 100:
                self.total_rewards = self.total_rewards[-100:]
            
            if self.visible_interface:
                logger.info(f"Episode {self.episode_count} ended with reward: {total_reward:.2f}")
            else:
                logger.debug(f"Episode {self.episode_count} ended with reward: {total_reward:.2f}")
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get statistics about the learning process.
        
        Returns:
            Dict: Learning statistics
        """
        with self._lock:
            buffer_stats = self.experience_buffer.get_stats()
            
            return {
                "buffer": buffer_stats,
                "training_steps": self.training_steps,
                "episode_count": self.episode_count,
                "update_count": self.update_count,
                "avg_reward_last_100": np.mean(self.total_rewards) if self.total_rewards else 0,
                "max_reward": np.max(self.total_rewards) if self.total_rewards else 0,
                "min_reward": np.min(self.total_rewards) if self.total_rewards else 0,
                "learning_rate": self.learning_rate,
                "discount_factor": self.discount_factor
            }
    
    def save(self, path: str) -> None:
        """
        Save the learning system to disk.
        
        Args:
            path: Path to save system to
        """
        with self._lock:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            
            buffer_path = os.path.join(os.path.dirname(path), "buffer.json")
            self.experience_buffer.save(buffer_path)
            
            data = {
                "learning_rate": self.learning_rate,
                "discount_factor": self.discount_factor,
                "target_update_frequency": self.target_update_frequency,
                "batch_size": self.batch_size,
                "update_count": self.update_count,
                "training_steps": self.training_steps,
                "episode_count": self.episode_count,
                "total_rewards": self.total_rewards
            }
            
            with open(path, "w") as f:
                json.dump(data, f)
            
            if self.visible_interface:
                logger.info(f"Saved accelerated learning system to {path}")
            else:
                logger.debug(f"Saved accelerated learning system to {path}")
    
    def load(self, path: str) -> bool:
        """
        Load the learning system from disk.
        
        Args:
            path: Path to load system from
            
        Returns:
            bool: True if successful, False otherwise
        """
        with self._lock:
            if not os.path.exists(path):
                if self.visible_interface:
                    logger.warning(f"Learning system file {path} does not exist")
                else:
                    logger.debug(f"Learning system file {path} does not exist")
                return False
            
            try:
                buffer_path = os.path.join(os.path.dirname(path), "buffer.json")
                buffer_loaded = self.experience_buffer.load(buffer_path)
                
                with open(path, "r") as f:
                    data = json.load(f)
                
                self.learning_rate = data.get("learning_rate", self.learning_rate)
                self.discount_factor = data.get("discount_factor", self.discount_factor)
                self.target_update_frequency = data.get("target_update_frequency", self.target_update_frequency)
                self.batch_size = data.get("batch_size", self.batch_size)
                self.update_count = data.get("update_count", 0)
                self.training_steps = data.get("training_steps", 0)
                self.episode_count = data.get("episode_count", 0)
                self.total_rewards = data.get("total_rewards", [])
                
                if self.visible_interface:
                    logger.info(f"Loaded accelerated learning system from {path}")
                    if not buffer_loaded:
                        logger.warning("Buffer could not be loaded")
                else:
                    logger.debug(f"Loaded accelerated learning system from {path}")
                    if not buffer_loaded:
                        logger.debug("Buffer could not be loaded")
                
                return True
                
            except Exception as e:
                if self.visible_interface:
                    logger.error(f"Failed to load learning system from {path}: {str(e)}")
                else:
                    logger.debug(f"Failed to load learning system from {path}: {str(e)}")
                
                return False

def create_accelerated_learning(
    buffer_capacity: int = 100000,
    batch_size: int = 64,
    learning_rate: float = 0.001,
    discount_factor: float = 0.99,
    visible_interface: bool = False
) -> AcceleratedLearning:
    """
    Create and return an accelerated learning system.
    
    Args:
        buffer_capacity: Maximum number of experiences to store
        batch_size: Number of experiences to sample for each update
        learning_rate: Learning rate for the optimizer
        discount_factor: Discount factor for future rewards
        visible_interface: Whether to show learning messages in the interface
        
    Returns:
        AcceleratedLearning: New accelerated learning system
    """
    return AcceleratedLearning(
        buffer_capacity=buffer_capacity,
        batch_size=batch_size,
        learning_rate=learning_rate,
        discount_factor=discount_factor,
        visible_interface=visible_interface
    )
