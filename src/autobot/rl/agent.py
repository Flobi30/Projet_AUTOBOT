from typing import Dict, Any, List, Tuple
import numpy as np
import random
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
                    
                    self.w1 = np.random.randn(state_size, 24) * 0.1
                    self.b1 = np.zeros(24)
                    self.w2 = np.random.randn(24, 24) * 0.1
                    self.b2 = np.zeros(24)
                    self.w3 = np.random.randn(24, action_size) * 0.1
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
        if np.random.rand() <= self.epsilon:
            return random.randrange(self.action_size)
        
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
            
        minibatch = random.sample(self.memory, batch_size)
        
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
