"""
Genetic Algorithm Parameter Optimizer for AUTOBOT
Phase 6 Implementation - Advanced Parameter Optimization
"""

import random
import numpy as np
from typing import Dict, List, Any, Tuple
import logging
from concurrent.futures import ThreadPoolExecutor
import multiprocessing
import pandas as pd

logger = logging.getLogger(__name__)

class GeneticOptimizer:
    """
    Genetic algorithm optimizer for trading strategy parameters.
    Optimized for AMD Ryzen 7 PRO 8700GE multi-core processing.
    """
    
    def __init__(self, population_size: int = 50, generations: int = 100, 
                 mutation_rate: float = 0.1, crossover_rate: float = 0.8):
        self.population_size = population_size
        self.generations = generations
        self.mutation_rate = mutation_rate
        self.crossover_rate = crossover_rate
        self.cpu_count = min(multiprocessing.cpu_count(), 16)
        
    def evolve_parameters(self, df: pd.DataFrame, parameter_ranges: Dict[str, Tuple[float, float]]) -> Dict[str, Any]:
        """Evolve optimal parameters using genetic algorithm"""
        population = self._create_initial_population(parameter_ranges)
        
        best_individual = None
        best_fitness = -float('inf')
        
        for generation in range(self.generations):
            with ThreadPoolExecutor(max_workers=self.cpu_count) as executor:
                fitness_scores = list(executor.map(
                    lambda individual: self._evaluate_fitness(df, individual, parameter_ranges),
                    population
                ))
            
            max_fitness_idx = np.argmax(fitness_scores)
            if fitness_scores[max_fitness_idx] > best_fitness:
                best_fitness = fitness_scores[max_fitness_idx]
                best_individual = population[max_fitness_idx].copy()
            
            population = self._select_and_reproduce(population, fitness_scores, parameter_ranges)
            
            if generation % 10 == 0:
                logger.info(f"Generation {generation}: Best fitness = {best_fitness:.4f}")
        
        return self._decode_individual(best_individual, parameter_ranges)
    
    def _create_initial_population(self, parameter_ranges: Dict[str, Tuple[float, float]]) -> List[List[float]]:
        """Create initial random population"""
        population = []
        for _ in range(self.population_size):
            individual = []
            for param_name, (min_val, max_val) in parameter_ranges.items():
                individual.append(random.uniform(min_val, max_val))
            population.append(individual)
        return population
    
    def _evaluate_fitness(self, df: pd.DataFrame, individual: List[float], 
                         parameter_ranges: Dict[str, Tuple[float, float]]) -> float:
        """Evaluate fitness of an individual"""
        params = self._decode_individual(individual, parameter_ranges)
        
        try:
            returns = self._simulate_strategy(df, params)
            sharpe_ratio = self._calculate_sharpe_ratio(returns)
            max_drawdown = self._calculate_max_drawdown(returns)
            
            fitness = sharpe_ratio - max_drawdown * 0.5
            return fitness
        except Exception as e:
            logger.warning(f"Fitness evaluation failed: {e}")
            return -1000.0
    
    def _simulate_strategy(self, df: pd.DataFrame, params: Dict[str, float]) -> pd.Series:
        """Simulate strategy with given parameters"""
        df_copy = df.copy()
        
        ma_short = params.get('ma_short', 5)
        ma_long = params.get('ma_long', 15)
        rsi_period = params.get('rsi_period', 14)
        rsi_oversold = params.get('rsi_oversold', 30)
        rsi_overbought = params.get('rsi_overbought', 70)
        
        df_copy['ma_short'] = df_copy['close'].rolling(int(ma_short)).mean()
        df_copy['ma_long'] = df_copy['close'].rolling(int(ma_long)).mean()
        
        delta = df_copy['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=int(rsi_period)).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=int(rsi_period)).mean()
        rs = gain / loss
        df_copy['rsi'] = 100 - (100 / (1 + rs))
        
        df_copy['signal'] = 0
        buy_condition = (df_copy['ma_short'] > df_copy['ma_long']) & (df_copy['rsi'] < rsi_overbought)
        sell_condition = (df_copy['ma_short'] < df_copy['ma_long']) | (df_copy['rsi'] > rsi_overbought)
        
        df_copy.loc[buy_condition, 'signal'] = 1
        df_copy.loc[sell_condition, 'signal'] = 0
        
        df_copy['returns'] = df_copy['close'].pct_change()
        df_copy['strategy_returns'] = df_copy['signal'].shift(1) * df_copy['returns']
        
        return df_copy['strategy_returns'].dropna()
    
    def _calculate_sharpe_ratio(self, returns: pd.Series) -> float:
        """Calculate Sharpe ratio"""
        if len(returns) == 0 or returns.std() == 0:
            return 0.0
        return returns.mean() / returns.std() * np.sqrt(252)
    
    def _calculate_max_drawdown(self, returns: pd.Series) -> float:
        """Calculate maximum drawdown"""
        cumulative = (1 + returns).cumprod()
        running_max = cumulative.expanding().max()
        drawdown = (cumulative - running_max) / running_max
        return abs(drawdown.min())
    
    def _select_and_reproduce(self, population: List[List[float]], fitness_scores: List[float], 
                            parameter_ranges: Dict[str, Tuple[float, float]]) -> List[List[float]]:
        """Select and reproduce population"""
        fitness_array = np.array(fitness_scores)
        fitness_array = fitness_array - fitness_array.min() + 1e-6
        probabilities = fitness_array / fitness_array.sum()
        
        new_population = []
        
        for _ in range(self.population_size):
            if random.random() < self.crossover_rate:
                parent1_idx = np.random.choice(len(population), p=probabilities)
                parent2_idx = np.random.choice(len(population), p=probabilities)
                child = self._crossover(population[parent1_idx], population[parent2_idx])
            else:
                parent_idx = np.random.choice(len(population), p=probabilities)
                child = population[parent_idx].copy()
            
            child = self._mutate(child, parameter_ranges)
            new_population.append(child)
        
        return new_population
    
    def _crossover(self, parent1: List[float], parent2: List[float]) -> List[float]:
        """Perform crossover between two parents"""
        crossover_point = random.randint(1, len(parent1) - 1)
        child = parent1[:crossover_point] + parent2[crossover_point:]
        return child
    
    def _mutate(self, individual: List[float], parameter_ranges: Dict[str, Tuple[float, float]]) -> List[float]:
        """Mutate an individual"""
        param_names = list(parameter_ranges.keys())
        
        for i, gene in enumerate(individual):
            if random.random() < self.mutation_rate:
                param_name = param_names[i]
                min_val, max_val = parameter_ranges[param_name]
                individual[i] = random.uniform(min_val, max_val)
        
        return individual
    
    def _decode_individual(self, individual: List[float], parameter_ranges: Dict[str, Tuple[float, float]]) -> Dict[str, float]:
        """Decode individual to parameter dictionary"""
        params = {}
        param_names = list(parameter_ranges.keys())
        
        for i, param_name in enumerate(param_names):
            params[param_name] = individual[i]
        
        return params
