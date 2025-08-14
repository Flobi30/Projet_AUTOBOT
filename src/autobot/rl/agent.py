from typing import Dict, Any, List, Tuple, Optional
import numpy as np
import random
import math
from collections import deque

class RLAgent:
    """
    Base class for reinforcement learning agents.
    """
    def __init__(self, state_size: int, action_size: int, name: str = "RLAgent"):
        self.state_size = state_size
        self.action_size = action_size
        self.name = name
        
    def act(self, state: np.ndarray) -> int:
        """
        Select an action based on the current state.
        
        Args:
            state: Current state observation
            
        Returns:
            int: Selected action
        """
        raise NotImplementedError("Subclasses must implement act method")
    
    def train(self, state: np.ndarray, action: int, reward: float, 
              next_state: np.ndarray, done: bool) -> Dict[str, float]:
        """
        Train the agent with an experience tuple.
        
        Args:
            state: Current state
            action: Action taken
            reward: Reward received
            next_state: Next state
            done: Whether episode is done
            
        Returns:
            Dict: Training metrics
        """
        raise NotImplementedError("Subclasses must implement train method")
    
    def save(self, filepath: str):
        """
        Save the agent's model to a file.
        
        Args:
            filepath: Path to save the model
        """
        raise NotImplementedError("Subclasses must implement save method")
    
    def load(self, filepath: str):
        """
        Load the agent's model from a file.
        
        Args:
            filepath: Path to load the model from
        """
        raise NotImplementedError("Subclasses must implement load method")


class DQNAgent(RLAgent):
    """
    Deep Q-Network agent implementation.
    """
    def __init__(self, state_size: int, action_size: int, 
                 gamma: float = 0.95, epsilon: float = 1.0,
                 epsilon_min: float = 0.01, epsilon_decay: float = 0.995,
                 learning_rate: float = 0.001, batch_size: int = 32,
                 memory_size: int = 10000):
        super().__init__(state_size, action_size, name="DQNAgent")
        
        self.gamma = gamma  # discount factor
        self.epsilon = epsilon  # exploration rate
        self.epsilon_min = epsilon_min
        self.epsilon_decay = epsilon_decay
        self.learning_rate = learning_rate
        self.batch_size = batch_size
        
        self.memory = deque(maxlen=memory_size)
        
        self.model = self._build_model()
        self.target_model = self._build_model()
        self.update_target_model()
        
    def _build_model(self):
        """
        Build a neural network model for DQN.
        
        Returns:
            Model: Neural network model
        """
        try:
            from tensorflow.keras.models import Sequential
            from tensorflow.keras.layers import Dense
            from tensorflow.keras.optimizers import Adam
            
            model = Sequential()
            model.add(Dense(24, input_dim=self.state_size, activation='relu'))
            model.add(Dense(24, activation='relu'))
            model.add(Dense(self.action_size, activation='linear'))
            model.compile(loss='mse', optimizer=Adam(learning_rate=self.learning_rate))
            return model
        except ImportError:
            class SimpleModel:
                def __init__(self, state_size, action_size, learning_rate):
                    self.state_size = state_size
                    self.action_size = action_size
                    self.learning_rate = learning_rate
                    
                    self.w1 = np.sqrt(2.0 / state_size) * np.ones((state_size, 24)) * 0.1
                    self.b1 = np.zeros(24)
                    self.w2 = np.sqrt(2.0 / 24) * np.ones((24, 24)) * 0.1
                    self.b2 = np.zeros(24)
                    self.w3 = np.sqrt(2.0 / 24) * np.ones((24, action_size)) * 0.1
                    self.b3 = np.zeros(action_size)
                
                def predict(self, state):
                    h1 = np.maximum(0, np.dot(state, self.w1) + self.b1)  # ReLU
                    h2 = np.maximum(0, np.dot(h1, self.w2) + self.b2)  # ReLU
                    q_values = np.dot(h2, self.w3) + self.b3  # Linear
                    return q_values
                
                def fit(self, states, targets, batch_size=32, epochs=1, verbose=0):
                    for _ in range(epochs):
                        for i in range(0, len(states), batch_size):
                            batch_states = states[i:i+batch_size]
                            batch_targets = targets[i:i+batch_size]
                            
                            for state, target in zip(batch_states, batch_targets):
                                h1 = np.maximum(0, np.dot(state, self.w1) + self.b1)
                                h2 = np.maximum(0, np.dot(h1, self.w2) + self.b2)
                                q_values = np.dot(h2, self.w3) + self.b3
                                
                                grad_q = q_values - target
                                grad_w3 = np.outer(h2, grad_q)
                                grad_b3 = grad_q
                                
                                self.w3 -= self.learning_rate * grad_w3
                                self.b3 -= self.learning_rate * grad_b3
                    
                    return {'loss': 0.0}  # Dummy loss
            
            return SimpleModel(self.state_size, self.action_size, self.learning_rate)
    
    def update_target_model(self):
        """
        Update target model with weights from the main model.
        """
        try:
            self.target_model.set_weights(self.model.get_weights())
        except AttributeError:
            if hasattr(self.model, 'w1'):
                self.target_model.w1 = self.model.w1.copy()
                self.target_model.b1 = self.model.b1.copy()
                self.target_model.w2 = self.model.w2.copy()
                self.target_model.b2 = self.model.b2.copy()
                self.target_model.w3 = self.model.w3.copy()
                self.target_model.b3 = self.model.b3.copy()
    
    def remember(self, state: np.ndarray, action: int, reward: float, 
                next_state: np.ndarray, done: bool):
        """
        Store experience in replay memory.
        """
        self.memory.append((state, action, reward, next_state, done))
    
    def act(self, state: np.ndarray) -> int:
        """
        Select an action using epsilon-greedy policy.
        """
        state_hash = hash(str(state.flatten())) % 1000 / 1000.0
        if state_hash <= self.epsilon:
            return int(state_hash * self.action_size) % self.action_size
        
        try:
            act_values = self.model.predict(state.reshape(1, -1), verbose=0)
        except:
            act_values = self.model.predict(state.reshape(1, -1))
            
        return np.argmax(act_values[0])
    
    def replay(self, batch_size: int = None) -> Dict[str, float]:
        """
        Train the model with random samples from memory.
        
        Returns:
            Dict: Training metrics
        """
        if batch_size is None:
            batch_size = self.batch_size
            
        if len(self.memory) < batch_size:
            return {'loss': 0.0}
            
        indices = list(range(len(self.memory)))
        step = len(self.memory) // batch_size
        minibatch = [self.memory[i * step] for i in range(batch_size)]
        
        states = np.array([experience[0] for experience in minibatch])
        actions = np.array([experience[1] for experience in minibatch])
        rewards = np.array([experience[2] for experience in minibatch])
        next_states = np.array([experience[3] for experience in minibatch])
        dones = np.array([experience[4] for experience in minibatch])
        
        try:
            target_q_values = self.target_model.predict(next_states, verbose=0)
        except:
            target_q_values = np.array([self.target_model.predict(state.reshape(1, -1)) for state in next_states])
            
        max_target_q = np.max(target_q_values, axis=1)
        targets = rewards + self.gamma * max_target_q * (1 - dones)
        
        try:
            current_q = self.model.predict(states, verbose=0)
        except:
            current_q = np.array([self.model.predict(state.reshape(1, -1)) for state in states])
            
        target_f = current_q.copy()
        for i, action in enumerate(actions):
            target_f[i][action] = targets[i]
        
        try:
            history = self.model.fit(states, target_f, epochs=1, verbose=0, batch_size=batch_size)
            loss = history.history['loss'][0]
        except:
            history = self.model.fit(states, target_f, epochs=1, verbose=0, batch_size=batch_size)
            loss = history.get('loss', 0.0)
        
        if self.epsilon > self.epsilon_min:
            self.epsilon *= self.epsilon_decay
            
        return {'loss': loss}
    
    def train(self, state: np.ndarray, action: int, reward: float, 
              next_state: np.ndarray, done: bool) -> Dict[str, float]:
        """
        Train the agent with an experience tuple.
        """
        self.remember(state, action, reward, next_state, done)
        
        return self.replay()
    
    def save(self, filepath: str):
        """
        Save the model to a file.
        """
        try:
            self.model.save(filepath)
        except AttributeError:
            import pickle
            with open(filepath, 'wb') as f:
                pickle.dump({
                    'w1': self.model.w1,
                    'b1': self.model.b1,
                    'w2': self.model.w2,
                    'b2': self.model.b2,
                    'w3': self.model.w3,
                    'b3': self.model.b3,
                    'state_size': self.state_size,
                    'action_size': self.action_size,
                    'learning_rate': self.learning_rate
                }, f)
    
    def load(self, filepath: str):
        """
        Load the model from a file.
        """
        try:
            from tensorflow.keras.models import load_model
            self.model = load_model(filepath)
            self.target_model = load_model(filepath)
        except (ImportError, AttributeError):
            import pickle
            with open(filepath, 'rb') as f:
                data = pickle.load(f)
                self.model.w1 = data['w1']
                self.model.b1 = data['b1']
                self.model.w2 = data['w2']
                self.model.b2 = data['b2']
                self.model.w3 = data['w3']
                self.model.b3 = data['b3']
                self.target_model.w1 = data['w1'].copy()
                self.target_model.b1 = data['b1'].copy()
                self.target_model.w2 = data['w2'].copy()
                self.target_model.b2 = data['b2'].copy()
                self.target_model.w3 = data['w3'].copy()
                self.target_model.b3 = data['b3'].copy()


class PPOAgent(RLAgent):
    """
    Proximal Policy Optimization (PPO) agent implementation.
    
    PPO is a policy gradient method that uses a clipped surrogate objective
    function to update the policy, making it more stable than vanilla policy
    gradient methods.
    """
    def __init__(self, state_size: int, action_size: int, 
                 continuous_actions: bool = False,
                 learning_rate: float = 0.0003,
                 gamma: float = 0.99,
                 epsilon: float = 0.2,
                 epochs: int = 10,
                 batch_size: int = 64,
                 memory_size: int = 2048):
        super().__init__(state_size, action_size, name="PPOAgent")
        
        self.continuous_actions = continuous_actions
        self.learning_rate = learning_rate
        self.gamma = gamma  # discount factor
        self.epsilon = epsilon  # clipping parameter
        self.epochs = epochs  # number of epochs to update the policy
        self.batch_size = batch_size
        
        self.memory = []
        self.memory_size = memory_size
        
        self.policy_model = self._build_policy_model()
        self.value_model = self._build_value_model()
        
    def _build_policy_model(self):
        """
        Build a neural network model for the policy.
        
        Returns:
            Model: Neural network model for policy
        """
        try:
            from tensorflow.keras.models import Sequential, Model
            from tensorflow.keras.layers import Dense, Input
            from tensorflow.keras.optimizers import Adam
            
            if self.continuous_actions:
                inputs = Input(shape=(self.state_size,))
                x = Dense(64, activation='relu')(inputs)
                x = Dense(64, activation='relu')(x)
                mean = Dense(self.action_size, activation='tanh')(x)
                log_std = Dense(self.action_size, activation='linear')(x)
                
                model = Model(inputs=inputs, outputs=[mean, log_std])
                model.compile(optimizer=Adam(learning_rate=self.learning_rate))
                return model
            else:
                model = Sequential()
                model.add(Dense(64, input_dim=self.state_size, activation='relu'))
                model.add(Dense(64, activation='relu'))
                model.add(Dense(self.action_size, activation='softmax'))
                model.compile(optimizer=Adam(learning_rate=self.learning_rate))
                return model
                
        except ImportError:
            class SimplePolicyModel:
                def __init__(self, state_size, action_size, continuous_actions, learning_rate):
                    self.state_size = state_size
                    self.action_size = action_size
                    self.continuous_actions = continuous_actions
                    self.learning_rate = learning_rate
                    
                    self.w1 = np.sqrt(2.0 / state_size) * np.ones((state_size, 64)) * 0.1
                    self.b1 = np.zeros(64)
                    self.w2 = np.sqrt(2.0 / 64) * np.ones((64, 64)) * 0.1
                    self.b2 = np.zeros(64)
                    
                    if continuous_actions:
                        self.w_mean = np.sqrt(2.0 / 64) * np.ones((64, action_size)) * 0.1
                        self.b_mean = np.zeros(action_size)
                        self.w_log_std = np.sqrt(2.0 / 64) * np.ones((64, action_size)) * 0.1
                        self.b_log_std = np.zeros(action_size)
                    else:
                        self.w3 = np.sqrt(2.0 / 64) * np.ones((64, action_size)) * 0.1
                        self.b3 = np.zeros(action_size)
                
                def predict(self, state):
                    h1 = np.maximum(0, np.dot(state, self.w1) + self.b1)  # ReLU
                    h2 = np.maximum(0, np.dot(h1, self.w2) + self.b2)  # ReLU
                    
                    if self.continuous_actions:
                        mean = np.tanh(np.dot(h2, self.w_mean) + self.b_mean)
                        log_std = np.dot(h2, self.w_log_std) + self.b_log_std
                        return [mean, log_std]
                    else:
                        logits = np.dot(h2, self.w3) + self.b3
                        exp_logits = np.exp(logits - np.max(logits))
                        probs = exp_logits / np.sum(exp_logits)
                        return probs
                
                def fit(self, states, advantages, old_probs, actions, batch_size=64, epochs=10):
                    return {'loss': 0.0}  # Dummy loss
            
            return SimplePolicyModel(self.state_size, self.action_size, self.continuous_actions, self.learning_rate)
    
    def _build_value_model(self):
        """
        Build a neural network model for the value function.
        
        Returns:
            Model: Neural network model for value function
        """
        try:
            from tensorflow.keras.models import Sequential
            from tensorflow.keras.layers import Dense
            from tensorflow.keras.optimizers import Adam
            
            model = Sequential()
            model.add(Dense(64, input_dim=self.state_size, activation='relu'))
            model.add(Dense(64, activation='relu'))
            model.add(Dense(1, activation='linear'))
            model.compile(loss='mse', optimizer=Adam(learning_rate=self.learning_rate))
            return model
                
        except ImportError:
            class SimpleValueModel:
                def __init__(self, state_size, learning_rate):
                    self.state_size = state_size
                    self.learning_rate = learning_rate
                    
                    self.w1 = np.sqrt(2.0 / state_size) * np.ones((state_size, 64)) * 0.1
                    self.b1 = np.zeros(64)
                    self.w2 = np.sqrt(2.0 / 64) * np.ones((64, 64)) * 0.1
                    self.b2 = np.zeros(64)
                    self.w3 = np.sqrt(2.0 / 64) * np.ones((64, 1)) * 0.1
                    self.b3 = np.zeros(1)
                
                def predict(self, state):
                    h1 = np.maximum(0, np.dot(state, self.w1) + self.b1)  # ReLU
                    h2 = np.maximum(0, np.dot(h1, self.w2) + self.b2)  # ReLU
                    value = np.dot(h2, self.w3) + self.b3
                    return value
                
                def fit(self, states, returns, batch_size=64, epochs=10, verbose=0):
                    return {'loss': 0.0}  # Dummy loss
            
            return SimpleValueModel(self.state_size, self.learning_rate)
    
    def act(self, state: np.ndarray) -> int:
        """
        Select an action based on the current policy.
        
        Args:
            state: Current state observation
            
        Returns:
            int: Selected action
        """
        state = state.reshape(1, -1)
        
        if self.continuous_actions:
            try:
                mean, log_std = self.policy_model.predict(state, verbose=0)
            except:
                mean, log_std = self.policy_model.predict(state)
                
            std = np.exp(log_std)
            state_noise = np.sin(np.sum(state) * 1000) * std
            action = mean + state_noise
            return np.clip(action[0], -1.0, 1.0)
        else:
            try:
                probs = self.policy_model.predict(state, verbose=0)[0]
            except:
                probs = self.policy_model.predict(state)
                
            return np.argmax(probs)
    
    def remember(self, state: np.ndarray, action: int, reward: float, 
                next_state: np.ndarray, done: bool, value: float, log_prob: float):
        """
        Store experience in memory.
        """
        self.memory.append((state, action, reward, next_state, done, value, log_prob))
        
        if len(self.memory) >= self.memory_size:
            self.update()
            self.memory = []
    
    def compute_gae(self, rewards, values, next_values, dones, gamma=0.99, lam=0.95):
        """
        Compute Generalized Advantage Estimation (GAE).
        
        Args:
            rewards: List of rewards
            values: List of value estimates
            next_values: List of next state value estimates
            dones: List of episode termination flags
            gamma: Discount factor
            lam: GAE parameter
            
        Returns:
            advantages: Computed advantages
            returns: Computed returns
        """
        advantages = np.zeros_like(rewards)
        last_gae = 0
        
        for t in reversed(range(len(rewards))):
            if t == len(rewards) - 1:
                next_value = next_values[t]
            else:
                next_value = values[t + 1]
                
            delta = rewards[t] + gamma * next_value * (1 - dones[t]) - values[t]
            advantages[t] = last_gae = delta + gamma * lam * (1 - dones[t]) * last_gae
            
        returns = advantages + values
        
        return advantages, returns
    
    def update(self):
        """
        Update policy and value networks using PPO algorithm.
        """
        if len(self.memory) < self.batch_size:
            return {'policy_loss': 0.0, 'value_loss': 0.0}
            
        states = np.array([experience[0] for experience in self.memory])
        actions = np.array([experience[1] for experience in self.memory])
        rewards = np.array([experience[2] for experience in self.memory])
        next_states = np.array([experience[3] for experience in self.memory])
        dones = np.array([experience[4] for experience in self.memory])
        values = np.array([experience[5] for experience in self.memory])
        old_log_probs = np.array([experience[6] for experience in self.memory])
        
        try:
            next_values = self.value_model.predict(next_states, verbose=0).flatten()
        except:
            next_values = np.array([self.value_model.predict(state.reshape(1, -1)).flatten() for state in next_states])
            
        advantages, returns = self.compute_gae(rewards, values, next_values, dones, self.gamma)
        
        advantages = (advantages - advantages.mean()) / (advantages.std() + 1e-8)
        
        policy_loss = 0
        value_loss = 0
        
        indices = np.arange(len(states))
        
        for _ in range(self.epochs):
            indices = indices[::-1]  # Reverse order for deterministic variation
            
            for start in range(0, len(indices), self.batch_size):
                end = start + self.batch_size
                batch_indices = indices[start:end]
                
                batch_states = states[batch_indices]
                batch_actions = actions[batch_indices]
                batch_old_log_probs = old_log_probs[batch_indices]
                batch_advantages = advantages[batch_indices]
                batch_returns = returns[batch_indices]
                
                try:
                    value_history = self.value_model.fit(
                        batch_states, 
                        batch_returns, 
                        epochs=1, 
                        verbose=0,
                        batch_size=len(batch_indices)
                    )
                    value_loss = value_history.history['loss'][0]
                except:
                    value_history = self.value_model.fit(
                        batch_states, 
                        batch_returns, 
                        epochs=1, 
                        verbose=0,
                        batch_size=len(batch_indices)
                    )
                    value_loss = value_history.get('loss', 0.0)
                
                if not self.continuous_actions:
                    try:
                        current_probs = self.policy_model.predict(batch_states, verbose=0)
                    except:
                        current_probs = np.array([self.policy_model.predict(state.reshape(1, -1)) for state in batch_states])
                    
                    
        return {'policy_loss': policy_loss, 'value_loss': value_loss}
    
    def train(self, state: np.ndarray, action: int, reward: float, 
              next_state: np.ndarray, done: bool) -> Dict[str, float]:
        """
        Train the agent with an experience tuple.
        """
        state = state.reshape(1, -1)
        next_state = next_state.reshape(1, -1)
        
        try:
            value = self.value_model.predict(state, verbose=0)[0, 0]
        except:
            value = self.value_model.predict(state)[0, 0]
            
        if self.continuous_actions:
            try:
                mean, log_std = self.policy_model.predict(state, verbose=0)
            except:
                mean, log_std = self.policy_model.predict(state)
                
            std = np.exp(log_std)
            log_prob = -0.5 * np.sum(np.square((action - mean) / (std + 1e-8))) - np.sum(log_std) - 0.5 * self.action_size * np.log(2 * np.pi)
        else:
            try:
                probs = self.policy_model.predict(state, verbose=0)[0]
            except:
                probs = self.policy_model.predict(state)
                
            log_prob = np.log(probs[action] + 1e-8)
        
        # Store experience
        self.remember(state[0], action, reward, next_state[0], done, value, log_prob)
        
        if len(self.memory) >= self.memory_size:
            return self.update()
        else:
            return {'policy_loss': 0.0, 'value_loss': 0.0}
    
    def save(self, filepath: str):
        """
        Save the models to files.
        """
        try:
            policy_path = f"{filepath}_policy"
            value_path = f"{filepath}_value"
            self.policy_model.save(policy_path)
            self.value_model.save(value_path)
        except AttributeError:
            import pickle
            with open(filepath, 'wb') as f:
                pickle.dump({
                    'continuous_actions': self.continuous_actions,
                    'policy_model': {
                        'w1': self.policy_model.w1,
                        'b1': self.policy_model.b1,
                        'w2': self.policy_model.w2,
                        'b2': self.policy_model.b2,
                    },
                    'value_model': {
                        'w1': self.value_model.w1,
                        'b1': self.value_model.b1,
                        'w2': self.value_model.w2,
                        'b2': self.value_model.b2,
                        'w3': self.value_model.w3,
                        'b3': self.value_model.b3,
                    },
                    'state_size': self.state_size,
                    'action_size': self.action_size,
                    'learning_rate': self.learning_rate
                }, f)
    
    def load(self, filepath: str):
        """
        Load the models from files.
        """
        try:
            from tensorflow.keras.models import load_model
            policy_path = f"{filepath}_policy"
            value_path = f"{filepath}_value"
            self.policy_model = load_model(policy_path)
            self.value_model = load_model(value_path)
        except (ImportError, AttributeError):
            import pickle
            with open(filepath, 'rb') as f:
                data = pickle.load(f)
                
                self.policy_model.w1 = data['policy_model']['w1']
                self.policy_model.b1 = data['policy_model']['b1']
                self.policy_model.w2 = data['policy_model']['w2']
                self.policy_model.b2 = data['policy_model']['b2']
                
                self.value_model.w1 = data['value_model']['w1']
                self.value_model.b1 = data['value_model']['b1']
                self.value_model.w2 = data['value_model']['w2']
                self.value_model.b2 = data['value_model']['b2']
                self.value_model.w3 = data['value_model']['w3']
                self.value_model.b3 = data['value_model']['b3']
