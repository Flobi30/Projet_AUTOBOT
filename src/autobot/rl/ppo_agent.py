"""
Proximal Policy Optimization (PPO) agent implementation for AUTOBOT.
"""
import os
import logging
import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
from torch.distributions import Normal
from typing import Dict, List, Tuple, Any, Optional, Union
import json
from datetime import datetime

logger = logging.getLogger(__name__)

class ActorCritic(nn.Module):
    """
    Actor-Critic network for PPO agent.
    """
    def __init__(
        self,
        state_dim: int,
        action_dim: int,
        hidden_dim: int = 256,
        std_init: float = 0.5
    ):
        """
        Initialize the Actor-Critic network.
        
        Args:
            state_dim: Dimension of state space
            action_dim: Dimension of action space
            hidden_dim: Dimension of hidden layers
            std_init: Initial standard deviation for action distribution
        """
        super(ActorCritic, self).__init__()
        
        self.actor = nn.Sequential(
            nn.Linear(state_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, action_dim)
        )
        
        self.critic = nn.Sequential(
            nn.Linear(state_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, 1)
        )
        
        self.log_std = nn.Parameter(torch.ones(action_dim) * np.log(std_init))
        
        self.apply(self._init_weights)
    
    def _init_weights(self, module):
        """Initialize network weights."""
        if isinstance(module, nn.Linear):
            nn.init.orthogonal_(module.weight, gain=np.sqrt(2))
            nn.init.zeros_(module.bias)
    
    def forward(self, state: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        Forward pass through the network.
        
        Args:
            state: State tensor
            
        Returns:
            Tuple of action mean and state value
        """
        action_mean = self.actor(state)
        state_value = self.critic(state)
        
        return action_mean, state_value
    
    def get_action(
        self,
        state: torch.Tensor,
        deterministic: bool = False
    ) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """
        Sample action from the policy.
        
        Args:
            state: State tensor
            deterministic: Whether to return deterministic action
            
        Returns:
            Tuple of action, log probability, and state value
        """
        action_mean, state_value = self.forward(state)
        
        if deterministic:
            return action_mean, None, state_value
        
        std = torch.exp(self.log_std)
        dist = Normal(action_mean, std)
        
        action = dist.sample()
        
        log_prob = dist.log_prob(action).sum(dim=-1, keepdim=True)
        
        return action, log_prob, state_value
    
    def evaluate_action(
        self,
        state: torch.Tensor,
        action: torch.Tensor
    ) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """
        Evaluate action log probability and entropy.
        
        Args:
            state: State tensor
            action: Action tensor
            
        Returns:
            Tuple of log probability, entropy, and state value
        """
        action_mean, state_value = self.forward(state)
        
        std = torch.exp(self.log_std)
        dist = Normal(action_mean, std)
        
        log_prob = dist.log_prob(action).sum(dim=-1, keepdim=True)
        entropy = dist.entropy().mean()
        
        return log_prob, entropy, state_value


class PPOBuffer:
    """
    Buffer for storing trajectories experienced by a PPO agent.
    """
    def __init__(
        self,
        state_dim: int,
        action_dim: int,
        buffer_size: int,
        gamma: float = 0.99,
        lam: float = 0.95
    ):
        """
        Initialize the buffer.
        
        Args:
            state_dim: Dimension of state space
            action_dim: Dimension of action space
            buffer_size: Maximum size of buffer
            gamma: Discount factor
            lam: GAE lambda parameter
        """
        self.states = np.zeros((buffer_size, state_dim), dtype=np.float32)
        self.actions = np.zeros((buffer_size, action_dim), dtype=np.float32)
        self.rewards = np.zeros(buffer_size, dtype=np.float32)
        self.values = np.zeros(buffer_size, dtype=np.float32)
        self.log_probs = np.zeros(buffer_size, dtype=np.float32)
        self.advantages = np.zeros(buffer_size, dtype=np.float32)
        self.returns = np.zeros(buffer_size, dtype=np.float32)
        self.dones = np.zeros(buffer_size, dtype=np.bool_)
        
        self.gamma = gamma
        self.lam = lam
        self.ptr = 0
        self.size = 0
        self.max_size = buffer_size
    
    def add(
        self,
        state: np.ndarray,
        action: np.ndarray,
        reward: float,
        value: float,
        log_prob: float,
        done: bool
    ):
        """
        Add a new experience to the buffer.
        
        Args:
            state: State
            action: Action
            reward: Reward
            value: Value estimate
            log_prob: Log probability of action
            done: Whether episode is done
        """
        assert self.ptr < self.max_size
        
        self.states[self.ptr] = state
        self.actions[self.ptr] = action
        self.rewards[self.ptr] = reward
        self.values[self.ptr] = value
        self.log_probs[self.ptr] = log_prob
        self.dones[self.ptr] = done
        
        self.ptr = (self.ptr + 1) % self.max_size
        self.size = min(self.size + 1, self.max_size)
    
    def compute_advantages(self, last_value: float, last_done: bool):
        """
        Compute advantages using Generalized Advantage Estimation (GAE).
        
        Args:
            last_value: Value estimate for the last state
            last_done: Whether the last state is terminal
        """
        gae = 0
        
        for i in reversed(range(self.size)):
            if i == self.size - 1:
                next_value = last_value
                next_non_terminal = 1.0 - last_done
            else:
                next_value = self.values[i + 1]
                next_non_terminal = 1.0 - self.dones[i + 1]
            
            delta = self.rewards[i] + self.gamma * next_value * next_non_terminal - self.values[i]
            gae = delta + self.gamma * self.lam * next_non_terminal * gae
            
            self.advantages[i] = gae
            self.returns[i] = gae + self.values[i]
    
    def get(self) -> Dict[str, torch.Tensor]:
        """
        Get all data from buffer.
        
        Returns:
            Dict of tensors containing buffer data
        """
        data = {
            "states": torch.FloatTensor(self.states[:self.size]),
            "actions": torch.FloatTensor(self.actions[:self.size]),
            "returns": torch.FloatTensor(self.returns[:self.size]).unsqueeze(1),
            "log_probs": torch.FloatTensor(self.log_probs[:self.size]).unsqueeze(1),
            "advantages": torch.FloatTensor(self.advantages[:self.size]).unsqueeze(1),
            "values": torch.FloatTensor(self.values[:self.size]).unsqueeze(1)
        }
        
        return data
    
    def clear(self):
        """Clear the buffer."""
        self.ptr = 0
        self.size = 0


class PPOAgent:
    """
    Proximal Policy Optimization (PPO) agent.
    """
    def __init__(
        self,
        state_dim: int,
        action_dim: int,
        hidden_dim: int = 256,
        lr: float = 3e-4,
        gamma: float = 0.99,
        lam: float = 0.95,
        clip_ratio: float = 0.2,
        value_coef: float = 0.5,
        entropy_coef: float = 0.01,
        max_grad_norm: float = 0.5,
        buffer_size: int = 2048,
        batch_size: int = 64,
        update_epochs: int = 10,
        device: str = "auto"
    ):
        """
        Initialize the PPO agent.
        
        Args:
            state_dim: Dimension of state space
            action_dim: Dimension of action space
            hidden_dim: Dimension of hidden layers
            lr: Learning rate
            gamma: Discount factor
            lam: GAE lambda parameter
            clip_ratio: PPO clip ratio
            value_coef: Value loss coefficient
            entropy_coef: Entropy loss coefficient
            max_grad_norm: Maximum gradient norm
            buffer_size: Maximum size of buffer
            batch_size: Batch size for updates
            update_epochs: Number of epochs to update policy per rollout
            device: Device to use for training (auto, cpu, cuda)
        """
        if device == "auto":
            self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        else:
            self.device = torch.device(device)
        
        logger.info(f"Using device: {self.device}")
        
        self.actor_critic = ActorCritic(state_dim, action_dim, hidden_dim).to(self.device)
        
        self.optimizer = optim.Adam(self.actor_critic.parameters(), lr=lr)
        
        self.buffer = PPOBuffer(state_dim, action_dim, buffer_size, gamma, lam)
        
        self.gamma = gamma
        self.lam = lam
        self.clip_ratio = clip_ratio
        self.value_coef = value_coef
        self.entropy_coef = entropy_coef
        self.max_grad_norm = max_grad_norm
        self.batch_size = batch_size
        self.update_epochs = update_epochs
        
        self.metrics = {
            "policy_loss": [],
            "value_loss": [],
            "entropy_loss": [],
            "total_loss": [],
            "approx_kl": [],
            "clip_fraction": [],
            "explained_variance": []
        }
        
        self.episode_rewards = []
        self.episode_lengths = []
        
        self.steps = 0
        
        self.hyperparameters = {
            "state_dim": state_dim,
            "action_dim": action_dim,
            "hidden_dim": hidden_dim,
            "lr": lr,
            "gamma": gamma,
            "lam": lam,
            "clip_ratio": clip_ratio,
            "value_coef": value_coef,
            "entropy_coef": entropy_coef,
            "max_grad_norm": max_grad_norm,
            "buffer_size": buffer_size,
            "batch_size": batch_size,
            "update_epochs": update_epochs
        }
    
    def select_action(
        self,
        state: np.ndarray,
        deterministic: bool = False
    ) -> Tuple[np.ndarray, float, float]:
        """
        Select action based on current policy.
        
        Args:
            state: State
            deterministic: Whether to select deterministic action
            
        Returns:
            Tuple of action, log probability, and value
        """
        state_tensor = torch.FloatTensor(state).unsqueeze(0).to(self.device)
        
        with torch.no_grad():
            action, log_prob, value = self.actor_critic.get_action(state_tensor, deterministic)
        
        action_np = action.cpu().numpy()[0]
        
        if log_prob is not None:
            log_prob_np = log_prob.cpu().numpy()[0, 0]
        else:
            log_prob_np = 0.0
            
        value_np = value.cpu().numpy()[0, 0]
        
        self.steps += 1
        
        return action_np, log_prob_np, value_np
    
    def store_transition(
        self,
        state: np.ndarray,
        action: np.ndarray,
        reward: float,
        value: float,
        log_prob: float,
        done: bool
    ):
        """
        Store transition in buffer.
        
        Args:
            state: State
            action: Action
            reward: Reward
            value: Value estimate
            log_prob: Log probability of action
            done: Whether episode is done
        """
        self.buffer.add(state, action, reward, value, log_prob, done)
    
    def finish_episode(self, last_value: float, last_done: bool):
        """
        Finish episode and compute advantages.
        
        Args:
            last_value: Value estimate for the last state
            last_done: Whether the last state is terminal
        """
        self.buffer.compute_advantages(last_value, last_done)
    
    def update(self) -> Dict[str, float]:
        """
        Update policy using PPO.
        
        Returns:
            Dict of training metrics
        """
        data = self.buffer.get()
        
        states = data["states"].to(self.device)
        actions = data["actions"].to(self.device)
        returns = data["returns"].to(self.device)
        old_log_probs = data["log_probs"].to(self.device)
        advantages = data["advantages"].to(self.device)
        old_values = data["values"].to(self.device)
        
        advantages = (advantages - advantages.mean()) / (advantages.std() + 1e-8)
        
        metrics = {
            "policy_loss": 0,
            "value_loss": 0,
            "entropy_loss": 0,
            "total_loss": 0,
            "approx_kl": 0,
            "clip_fraction": 0
        }
        
        for _ in range(self.update_epochs):
            indices = torch.randperm(states.size(0))
            
            for start in range(0, states.size(0), self.batch_size):
                end = start + self.batch_size
                batch_indices = indices[start:end]
                
                batch_states = states[batch_indices]
                batch_actions = actions[batch_indices]
                batch_returns = returns[batch_indices]
                batch_old_log_probs = old_log_probs[batch_indices]
                batch_advantages = advantages[batch_indices]
                batch_old_values = old_values[batch_indices]
                
                new_log_probs, entropy, new_values = self.actor_critic.evaluate_action(
                    batch_states, batch_actions
                )
                
                ratio = torch.exp(new_log_probs - batch_old_log_probs)
                surr1 = ratio * batch_advantages
                surr2 = torch.clamp(ratio, 1.0 - self.clip_ratio, 1.0 + self.clip_ratio) * batch_advantages
                policy_loss = -torch.min(surr1, surr2).mean()
                
                value_loss = 0.5 * ((new_values - batch_returns) ** 2).mean()
                
                entropy_loss = -entropy
                
                total_loss = policy_loss + self.value_coef * value_loss + self.entropy_coef * entropy_loss
                
                approx_kl = ((ratio - 1) - torch.log(ratio)).mean().item()
                
                clip_fraction = ((ratio - 1.0).abs() > self.clip_ratio).float().mean().item()
                
                metrics["policy_loss"] += policy_loss.item()
                metrics["value_loss"] += value_loss.item()
                metrics["entropy_loss"] += entropy_loss.item()
                metrics["total_loss"] += total_loss.item()
                metrics["approx_kl"] += approx_kl
                metrics["clip_fraction"] += clip_fraction
                
                self.optimizer.zero_grad()
                total_loss.backward()
                nn.utils.clip_grad_norm_(self.actor_critic.parameters(), self.max_grad_norm)
                self.optimizer.step()
        
        num_updates = self.update_epochs * (states.size(0) // self.batch_size + 1)
        for key in metrics:
            metrics[key] /= num_updates
            self.metrics[key].append(metrics[key])
        
        values_pred = data["values"].numpy()
        values_true = data["returns"].numpy()
        var_y = np.var(values_true)
        explained_var = np.nan if var_y == 0 else 1 - np.var(values_true - values_pred) / var_y
        metrics["explained_variance"] = explained_var
        self.metrics["explained_variance"].append(explained_var)
        
        self.buffer.clear()
        
        return metrics
    
    def save(self, path: str):
        """
        Save agent to disk.
        
        Args:
            path: Path to save agent
        """
        os.makedirs(os.path.dirname(path), exist_ok=True)
        
        torch.save({
            "actor_critic": self.actor_critic.state_dict(),
            "optimizer": self.optimizer.state_dict(),
            "hyperparameters": self.hyperparameters,
            "metrics": self.metrics,
            "steps": self.steps,
            "episode_rewards": self.episode_rewards,
            "episode_lengths": self.episode_lengths
        }, path)
        
        logger.info(f"Saved agent to {path}")
    
    def load(self, path: str):
        """
        Load agent from disk.
        
        Args:
            path: Path to load agent from
        """
        checkpoint = torch.load(path, map_location=self.device)
        
        hyperparameters = checkpoint["hyperparameters"]
        
        for key, value in hyperparameters.items():
            if key in ["state_dim", "action_dim"] and value != getattr(self, key, None):
                logger.warning(f"Hyperparameter mismatch: {key} = {value} (checkpoint) vs {getattr(self, key)} (agent)")
        
        self.actor_critic.load_state_dict(checkpoint["actor_critic"])
        self.optimizer.load_state_dict(checkpoint["optimizer"])
        
        self.metrics = checkpoint["metrics"]
        self.steps = checkpoint["steps"]
        self.episode_rewards = checkpoint["episode_rewards"]
        self.episode_lengths = checkpoint["episode_lengths"]
        
        logger.info(f"Loaded agent from {path}")
    
    def get_metrics(self) -> Dict[str, List[float]]:
        """
        Get training metrics.
        
        Returns:
            Dict of training metrics
        """
        return self.metrics
    
    def add_episode_metrics(self, reward: float, length: int):
        """
        Add episode metrics.
        
        Args:
            reward: Episode reward
            length: Episode length
        """
        self.episode_rewards.append(reward)
        self.episode_lengths.append(length)
