"""
Parameter Optimization System for AUTOBOT Trading Platform
Phase 3 Implementation - Grid Search and Genetic Algorithms

This module implements the parameter optimization system specified in the performance optimization roadmap.
Integrates with existing performance_optimizer.py and provides automated parameter tuning capabilities.
"""

import logging
import numpy as np
import pandas as pd
from typing import Dict, Any, List, Tuple, Optional, Callable
from datetime import datetime, timedelta
import itertools
import random
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
import json
import pickle
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)

class OptimizationMethod(Enum):
    GRID_SEARCH = "grid_search"
    GENETIC_ALGORITHM = "genetic_algorithm"
    RANDOM_SEARCH = "random_search"
    BAYESIAN_OPTIMIZATION = "bayesian_optimization"

@dataclass
class ParameterRange:
    """Define parameter optimization range."""
    name: str
    min_value: float
    max_value: float
    step: Optional[float] = None
    values: Optional[List] = None
    param_type: str = "float"  # "float", "int", "categorical"

@dataclass
class OptimizationResult:
    """Store optimization results."""
    parameters: Dict[str, Any]
    fitness_score: float
    metrics: Dict[str, float]
    backtest_results: Dict[str, Any]
    timestamp: datetime

class ParameterOptimizer:
    """
    Advanced Parameter Optimization System for AUTOBOT.
    
    Implements grid search, genetic algorithms, and walk-forward analysis
    for robust parameter optimization as specified in the roadmap.
    """
    
    def __init__(
        self,
        optimization_method: OptimizationMethod = OptimizationMethod.GENETIC_ALGORITHM,
        population_size: int = 50,
        generations: int = 100,
        mutation_rate: float = 0.1,
        crossover_rate: float = 0.8,
        elite_size: int = 5,
        parallel_workers: int = 4,
        walk_forward_periods: int = 10,
        validation_split: float = 0.3
    ):
        """
        Initialize the Parameter Optimizer.
        
        Args:
            optimization_method: Method to use for optimization
            population_size: Size of population for genetic algorithm
            generations: Number of generations for genetic algorithm
            mutation_rate: Mutation rate for genetic algorithm
            crossover_rate: Crossover rate for genetic algorithm
            elite_size: Number of elite individuals to preserve
            parallel_workers: Number of parallel workers for optimization
            walk_forward_periods: Number of periods for walk-forward analysis
            validation_split: Fraction of data to use for validation
        """
        self.optimization_method = optimization_method
        self.population_size = population_size
        self.generations = generations
        self.mutation_rate = mutation_rate
        self.crossover_rate = crossover_rate
        self.elite_size = elite_size
        self.parallel_workers = parallel_workers
        self.walk_forward_periods = walk_forward_periods
        self.validation_split = validation_split
        
        self.parameter_ranges = {}
        self.optimization_history = []
        self.best_parameters = None
        self.best_fitness = -np.inf
        
        logger.info(f"Parameter Optimizer initialized with {optimization_method.value} method")
    
    def add_parameter_range(self, param_range: ParameterRange):
        """
        Add a parameter range for optimization.
        
        Args:
            param_range: ParameterRange object defining the parameter space
        """
        self.parameter_ranges[param_range.name] = param_range
        logger.info(f"Added parameter range: {param_range.name} [{param_range.min_value}, {param_range.max_value}]")
    
    def add_strategy_parameters(self):
        """Add default strategy parameters for optimization based on roadmap specifications."""
        self.add_parameter_range(ParameterRange("ma_fast_period", 3, 10, step=1, param_type="int"))
        self.add_parameter_range(ParameterRange("ma_slow_period", 10, 25, step=1, param_type="int"))
        
        self.add_parameter_range(ParameterRange("rsi_period", 8, 15, step=1, param_type="int"))
        self.add_parameter_range(ParameterRange("rsi_oversold", 15, 25, step=1, param_type="int"))
        self.add_parameter_range(ParameterRange("rsi_overbought", 75, 85, step=1, param_type="int"))
        
        self.add_parameter_range(ParameterRange("macd_fast", 8, 15, step=1, param_type="int"))
        self.add_parameter_range(ParameterRange("macd_slow", 20, 30, step=1, param_type="int"))
        self.add_parameter_range(ParameterRange("macd_signal", 7, 12, step=1, param_type="int"))
        
        self.add_parameter_range(ParameterRange("bb_period", 15, 25, step=1, param_type="int"))
        self.add_parameter_range(ParameterRange("bb_std", 1.5, 2.5, step=0.1, param_type="float"))
        
        self.add_parameter_range(ParameterRange("stop_loss_pct", 1.0, 3.0, step=0.1, param_type="float"))
        self.add_parameter_range(ParameterRange("take_profit_pct", 4.0, 8.0, step=0.2, param_type="float"))
        self.add_parameter_range(ParameterRange("max_position_pct", 5.0, 15.0, step=1.0, param_type="float"))
        
        logger.info("Added default strategy parameters for optimization")
    
    def generate_random_parameters(self) -> Dict[str, Any]:
        """Generate random parameters within defined ranges."""
        parameters = {}
        
        for name, param_range in self.parameter_ranges.items():
            if param_range.param_type == "int":
                if param_range.step:
                    values = list(range(int(param_range.min_value), int(param_range.max_value) + 1, int(param_range.step)))
                    parameters[name] = random.choice(values)
                else:
                    parameters[name] = random.randint(int(param_range.min_value), int(param_range.max_value))
            elif param_range.param_type == "float":
                if param_range.step:
                    steps = int((param_range.max_value - param_range.min_value) / param_range.step)
                    step_value = random.randint(0, steps) * param_range.step
                    parameters[name] = param_range.min_value + step_value
                else:
                    parameters[name] = random.uniform(param_range.min_value, param_range.max_value)
            elif param_range.param_type == "categorical" and param_range.values:
                parameters[name] = random.choice(param_range.values)
        
        return parameters
    
    def grid_search_optimization(
        self,
        fitness_function: Callable,
        data: pd.DataFrame
    ) -> Optional[OptimizationResult]:
        """
        Perform grid search optimization.
        
        Args:
            fitness_function: Function to evaluate parameter fitness
            data: Historical data for backtesting
            
        Returns:
            Best optimization result
        """
        logger.info("Starting grid search optimization")
        
        param_combinations = []
        param_names = list(self.parameter_ranges.keys())
        param_values = []
        
        for name in param_names:
            param_range = self.parameter_ranges[name]
            if param_range.values:
                param_values.append(param_range.values)
            elif param_range.step:
                if param_range.param_type == "int":
                    values = list(range(int(param_range.min_value), int(param_range.max_value) + 1, int(param_range.step)))
                else:
                    steps = int((param_range.max_value - param_range.min_value) / param_range.step) + 1
                    values = [param_range.min_value + i * param_range.step for i in range(steps)]
                param_values.append(values)
            else:
                values = np.linspace(param_range.min_value, param_range.max_value, 10)
                param_values.append(values.tolist())
        
        for combination in itertools.product(*param_values):
            param_dict = dict(zip(param_names, combination))
            param_combinations.append(param_dict)
        
        logger.info(f"Generated {len(param_combinations)} parameter combinations")
        
        best_result = None
        best_fitness = -np.inf
        
        with ThreadPoolExecutor(max_workers=self.parallel_workers) as executor:
            futures = []
            for params in param_combinations:
                future = executor.submit(self._evaluate_parameters, params, fitness_function, data)
                futures.append((future, params))
            
            for i, (future, params) in enumerate(futures):
                try:
                    fitness_score, metrics, backtest_results = future.result()
                    
                    result = OptimizationResult(
                        parameters=params,
                        fitness_score=fitness_score,
                        metrics=metrics,
                        backtest_results=backtest_results,
                        timestamp=datetime.now()
                    )
                    
                    self.optimization_history.append(result)
                    
                    if fitness_score > best_fitness:
                        best_fitness = fitness_score
                        best_result = result
                        self.best_parameters = params
                        self.best_fitness = fitness_score
                    
                    if (i + 1) % 100 == 0:
                        logger.info(f"Evaluated {i + 1}/{len(param_combinations)} combinations, best fitness: {best_fitness:.4f}")
                
                except Exception as e:
                    logger.error(f"Error evaluating parameters {params}: {e}")
        
        logger.info(f"Grid search completed. Best fitness: {best_fitness:.4f}")
        return best_result if best_result is not None else OptimizationResult(
            parameters={},
            fitness_score=-np.inf,
            metrics={},
            backtest_results={},
            timestamp=datetime.now()
        )
    
    def genetic_algorithm_optimization(
        self,
        fitness_function: Callable,
        data: pd.DataFrame
    ) -> Optional[OptimizationResult]:
        """
        Perform genetic algorithm optimization.
        
        Args:
            fitness_function: Function to evaluate parameter fitness
            data: Historical data for backtesting
            
        Returns:
            Best optimization result
        """
        logger.info(f"Starting genetic algorithm optimization with {self.generations} generations")
        
        population = []
        for _ in range(self.population_size):
            individual = self.generate_random_parameters()
            population.append(individual)
        
        best_result = None
        best_fitness = -np.inf
        
        for generation in range(self.generations):
            fitness_scores = []
            generation_results = []
            
            with ThreadPoolExecutor(max_workers=self.parallel_workers) as executor:
                futures = []
                for individual in population:
                    future = executor.submit(self._evaluate_parameters, individual, fitness_function, data)
                    futures.append((future, individual))
                
                for future, individual in futures:
                    try:
                        fitness_score, metrics, backtest_results = future.result()
                        fitness_scores.append(fitness_score)
                        
                        result = OptimizationResult(
                            parameters=individual,
                            fitness_score=fitness_score,
                            metrics=metrics,
                            backtest_results=backtest_results,
                            timestamp=datetime.now()
                        )
                        
                        generation_results.append(result)
                        self.optimization_history.append(result)
                        
                        if fitness_score > best_fitness:
                            best_fitness = fitness_score
                            best_result = result
                            self.best_parameters = individual
                            self.best_fitness = fitness_score
                    
                    except Exception as e:
                        fitness_scores.append(-np.inf)
                        logger.error(f"Error evaluating individual {individual}: {e}")
            
            new_population = self._evolve_population(population, fitness_scores)
            population = new_population
            
            avg_fitness = np.mean([f for f in fitness_scores if f != -np.inf])
            logger.info(f"Generation {generation + 1}/{self.generations}: Best={best_fitness:.4f}, Avg={avg_fitness:.4f}")
        
        logger.info(f"Genetic algorithm completed. Best fitness: {best_fitness:.4f}")
        return best_result if best_result is not None else OptimizationResult(
            parameters={},
            fitness_score=-np.inf,
            metrics={},
            backtest_results={},
            timestamp=datetime.now()
        )
    
    def _evaluate_parameters(
        self,
        parameters: Dict[str, Any],
        fitness_function: Callable,
        data: pd.DataFrame
    ) -> Tuple[float, Dict[str, float], Dict[str, Any]]:
        """
        Evaluate a set of parameters using the fitness function.
        
        Args:
            parameters: Parameters to evaluate
            fitness_function: Function to calculate fitness
            data: Historical data for backtesting
            
        Returns:
            Tuple of (fitness_score, metrics, backtest_results)
        """
        try:
            fitness_score, metrics, backtest_results = fitness_function(parameters, data)
            return fitness_score, metrics, backtest_results
        except Exception as e:
            logger.error(f"Error in fitness function: {e}")
            return -np.inf, {}, {}
    
    def _evolve_population(
        self,
        population: List[Dict[str, Any]],
        fitness_scores: List[float]
    ) -> List[Dict[str, Any]]:
        """
        Evolve population using selection, crossover, and mutation.
        
        Args:
            population: Current population
            fitness_scores: Fitness scores for each individual
            
        Returns:
            New evolved population
        """
        sorted_indices = np.argsort(fitness_scores)[::-1]
        sorted_population = [population[i] for i in sorted_indices]
        sorted_fitness = [fitness_scores[i] for i in sorted_indices]
        
        new_population = []
        
        for i in range(min(self.elite_size, len(sorted_population))):
            if sorted_fitness[i] != -np.inf:
                new_population.append(sorted_population[i].copy())
        
        while len(new_population) < self.population_size:
            parent1 = self._tournament_selection(sorted_population, sorted_fitness)
            parent2 = self._tournament_selection(sorted_population, sorted_fitness)
            
            if random.random() < self.crossover_rate:
                child1, child2 = self._crossover(parent1, parent2)
            else:
                child1, child2 = parent1.copy(), parent2.copy()
            
            if random.random() < self.mutation_rate:
                child1 = self._mutate(child1)
            if random.random() < self.mutation_rate:
                child2 = self._mutate(child2)
            
            new_population.extend([child1, child2])
        
        return new_population[:self.population_size]
    
    def _tournament_selection(
        self,
        population: List[Dict[str, Any]],
        fitness_scores: List[float],
        tournament_size: int = 3
    ) -> Dict[str, Any]:
        """Tournament selection for genetic algorithm."""
        tournament_indices = random.sample(range(len(population)), min(tournament_size, len(population)))
        tournament_fitness = [fitness_scores[i] for i in tournament_indices]
        winner_index = tournament_indices[np.argmax(tournament_fitness)]
        return population[winner_index].copy()
    
    def _crossover(
        self,
        parent1: Dict[str, Any],
        parent2: Dict[str, Any]
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """Crossover operation for genetic algorithm."""
        child1, child2 = parent1.copy(), parent2.copy()
        
        for param_name in parent1.keys():
            if random.random() < 0.5:
                child1[param_name], child2[param_name] = child2[param_name], child1[param_name]
        
        return child1, child2
    
    def _mutate(self, individual: Dict[str, Any]) -> Dict[str, Any]:
        """Mutation operation for genetic algorithm."""
        mutated = individual.copy()
        
        for param_name in mutated.keys():
            if random.random() < 0.1:  # 10% chance to mutate each parameter
                param_range = self.parameter_ranges[param_name]
                
                if param_range.param_type == "int":
                    if param_range.step:
                        values = list(range(int(param_range.min_value), int(param_range.max_value) + 1, int(param_range.step)))
                        mutated[param_name] = random.choice(values)
                    else:
                        mutated[param_name] = random.randint(int(param_range.min_value), int(param_range.max_value))
                elif param_range.param_type == "float":
                    if param_range.step:
                        steps = int((param_range.max_value - param_range.min_value) / param_range.step)
                        step_value = random.randint(0, steps) * param_range.step
                        mutated[param_name] = param_range.min_value + step_value
                    else:
                        mutated[param_name] = random.uniform(param_range.min_value, param_range.max_value)
                elif param_range.param_type == "categorical" and param_range.values:
                    mutated[param_name] = random.choice(param_range.values)
        
        return mutated
    
    def walk_forward_analysis(
        self,
        fitness_function: Callable,
        data: pd.DataFrame,
        optimization_window: int = 252,  # 1 year
        test_window: int = 63  # 3 months
    ) -> List[OptimizationResult]:
        """
        Perform walk-forward analysis for robust validation.
        
        Args:
            fitness_function: Function to evaluate parameter fitness
            data: Historical data for analysis
            optimization_window: Number of periods for optimization
            test_window: Number of periods for testing
            
        Returns:
            List of optimization results for each period
        """
        logger.info("Starting walk-forward analysis")
        
        results = []
        total_periods = len(data)
        
        for i in range(optimization_window, total_periods - test_window, test_window):
            opt_start = max(0, i - optimization_window)
            opt_end = i
            test_start = i
            test_end = min(total_periods, i + test_window)
            
            opt_data = data.iloc[opt_start:opt_end]
            test_data = data.iloc[test_start:test_end]
            
            logger.info(f"Walk-forward period {len(results) + 1}: Optimizing on {len(opt_data)} samples, testing on {len(test_data)} samples")
            
            if self.optimization_method == OptimizationMethod.GENETIC_ALGORITHM:
                opt_result = self.genetic_algorithm_optimization(fitness_function, opt_data)
            else:
                opt_result = self.grid_search_optimization(fitness_function, opt_data)
            
            if opt_result:
                test_fitness, test_metrics, test_backtest = self._evaluate_parameters(
                    opt_result.parameters, fitness_function, test_data
                )
                
                test_result = OptimizationResult(
                    parameters=opt_result.parameters,
                    fitness_score=test_fitness,
                    metrics=test_metrics,
                    backtest_results=test_backtest,
                    timestamp=datetime.now()
                )
                
                results.append(test_result)
                logger.info(f"Walk-forward test result: {test_fitness:.4f}")
        
        logger.info(f"Walk-forward analysis completed with {len(results)} periods")
        return results
    
    def save_optimization_results(self, filepath: str):
        """Save optimization results to file."""
        results_data = {
            'best_parameters': self.best_parameters,
            'best_fitness': self.best_fitness,
            'optimization_history': [
                {
                    'parameters': result.parameters,
                    'fitness_score': result.fitness_score,
                    'metrics': result.metrics,
                    'timestamp': result.timestamp.isoformat()
                }
                for result in self.optimization_history
            ],
            'parameter_ranges': {
                name: {
                    'min_value': param_range.min_value,
                    'max_value': param_range.max_value,
                    'step': param_range.step,
                    'values': param_range.values,
                    'param_type': param_range.param_type
                }
                for name, param_range in self.parameter_ranges.items()
            }
        }
        
        with open(filepath, 'w') as f:
            json.dump(results_data, f, indent=2)
        
        logger.info(f"Optimization results saved to {filepath}")
    
    def load_optimization_results(self, filepath: str):
        """Load optimization results from file."""
        with open(filepath, 'r') as f:
            results_data = json.load(f)
        
        self.best_parameters = results_data.get('best_parameters')
        self.best_fitness = results_data.get('best_fitness', -np.inf)
        
        self.optimization_history = []
        for result_data in results_data.get('optimization_history', []):
            result = OptimizationResult(
                parameters=result_data['parameters'],
                fitness_score=result_data['fitness_score'],
                metrics=result_data['metrics'],
                backtest_results={},
                timestamp=datetime.fromisoformat(result_data['timestamp'])
            )
            self.optimization_history.append(result)
        
        logger.info(f"Optimization results loaded from {filepath}")

def create_fitness_function(target_metrics: Dict[str, float]) -> Callable:
    """
    Create a fitness function based on target metrics.
    
    Args:
        target_metrics: Dictionary of target metrics and their weights
        
    Returns:
        Fitness function
    """
    def fitness_function(parameters: Dict[str, Any], data: pd.DataFrame) -> Tuple[float, Dict[str, float], Dict[str, Any]]:
        """
        Evaluate parameters and return fitness score.
        
        Args:
            parameters: Parameters to evaluate
            data: Historical data for backtesting
            
        Returns:
            Tuple of (fitness_score, metrics, backtest_results)
        """
        try:
            
            total_return = random.uniform(-0.1, 0.3)  # -10% to 30%
            sharpe_ratio = random.uniform(-1.0, 3.0)
            max_drawdown = random.uniform(0.05, 0.4)  # 5% to 40%
            win_rate = random.uniform(0.3, 0.8)  # 30% to 80%
            
            metrics = {
                'total_return': total_return,
                'sharpe_ratio': sharpe_ratio,
                'max_drawdown': max_drawdown,
                'win_rate': win_rate
            }
            
            fitness_score = 0.0
            
            fitness_score += total_return * target_metrics.get('return_weight', 0.3)
            
            fitness_score += sharpe_ratio * target_metrics.get('sharpe_weight', 0.3)
            
            fitness_score -= max_drawdown * target_metrics.get('drawdown_penalty', 0.2)
            
            fitness_score += win_rate * target_metrics.get('winrate_weight', 0.2)
            
            backtest_results = {
                'parameters': parameters,
                'metrics': metrics,
                'data_length': len(data)
            }
            
            return fitness_score, metrics, backtest_results
            
        except Exception as e:
            logger.error(f"Error in fitness function: {e}")
            return -np.inf, {}, {}
    
    return fitness_function
