"""
Performance Optimizer for AUTOBOT
Intelligent data cleaning system that removes obsolete and non-performing data
while preserving important results and optimizing workspace efficiency.
"""

import logging
import sqlite3
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
import json
import os
from pathlib import Path

from ..db.models import SessionLocal, BacktestResult, CapitalHistory

logger = logging.getLogger(__name__)

class PerformanceOptimizer:
    """
    Intelligent data cleaning and optimization system for AUTOBOT.
    
    Features:
    - Removes obsolete backtest results that are no longer relevant
    - Cleans up non-performing strategies to free workspace
    - Preserves high-performing and recent results
    - Optimizes database size while maintaining historical insights
    - Manages log files and temporary data
    """
    
    def __init__(self, database_path: str = "data/autobot.db"):
        self.database_path = database_path
        self.performance_threshold = -5.0  # Remove strategies with < -5% return
        self.obsolete_days = 30  # Consider data older than 30 days as potentially obsolete
        self.max_records_per_strategy = 100  # Keep max 100 records per strategy
        self.min_records_to_keep = 1000  # Always keep at least 1000 best records
        
    def analyze_database_health(self) -> Dict:
        """Analyze current database state and identify optimization opportunities."""
        try:
            db = SessionLocal()
            
            total_records = db.query(BacktestResult).count()
            
            high_performers = db.query(BacktestResult).filter(
                BacktestResult.total_return > 5.0
            ).count()
            
            poor_performers = db.query(BacktestResult).filter(
                BacktestResult.total_return < self.performance_threshold
            ).count()
            
            cutoff_date = datetime.utcnow() - timedelta(days=self.obsolete_days)
            obsolete_records = db.query(BacktestResult).filter(
                BacktestResult.timestamp < cutoff_date,
                BacktestResult.total_return < 0
            ).count()
            
            strategies = db.query(BacktestResult.strategy).distinct().all()
            strategy_counts = {}
            for strategy in strategies:
                count = db.query(BacktestResult).filter(
                    BacktestResult.strategy == strategy[0]
                ).count()
                strategy_counts[strategy[0]] = count
            
            db.close()
            
            db_size = 0
            if os.path.exists(self.database_path):
                db_size = os.path.getsize(self.database_path) / (1024 * 1024)  # MB
            
            return {
                'total_records': total_records,
                'high_performers': high_performers,
                'poor_performers': poor_performers,
                'obsolete_records': obsolete_records,
                'strategy_counts': strategy_counts,
                'database_size_mb': round(db_size, 2),
                'optimization_potential': poor_performers + obsolete_records,
                'health_score': self._calculate_health_score(
                    total_records, high_performers, poor_performers, obsolete_records
                )
            }
            
        except Exception as e:
            logger.error(f"Error analyzing database health: {e}")
            return {'error': str(e)}
    
    def _calculate_health_score(self, total: int, high: int, poor: int, obsolete: int) -> float:
        """Calculate database health score (0-100)."""
        if total == 0:
            return 100.0
        
        high_ratio = high / total
        poor_ratio = poor / total
        obsolete_ratio = obsolete / total
        
        score = 100 * (high_ratio - poor_ratio - obsolete_ratio * 0.5)
        return max(0.0, min(100.0, score))
    
    def clean_obsolete_data(self, dry_run: bool = True) -> Dict:
        """
        Remove obsolete and non-performing data while preserving important results.
        
        Args:
            dry_run: If True, only analyze what would be cleaned without actually deleting
        
        Returns:
            Dictionary with cleaning results and statistics
        """
        try:
            db = SessionLocal()
            
            cutoff_date = datetime.utcnow() - timedelta(days=self.obsolete_days)
            
            obsolete_poor_query = db.query(BacktestResult).filter(
                BacktestResult.timestamp < cutoff_date,
                BacktestResult.total_return < self.performance_threshold
            )
            
            obsolete_poor_records = obsolete_poor_query.all()
            
            strategies_to_trim = []
            for strategy_name in db.query(BacktestResult.strategy).distinct():
                strategy = strategy_name[0]
                count = db.query(BacktestResult).filter(
                    BacktestResult.strategy == strategy
                ).count()
                
                if count > self.max_records_per_strategy:
                    worst_records = db.query(BacktestResult).filter(
                        BacktestResult.strategy == strategy
                    ).order_by(BacktestResult.total_return.asc()).limit(
                        count - self.max_records_per_strategy
                    ).all()
                    
                    strategies_to_trim.extend(worst_records)
            
            records_to_clean = list(set(obsolete_poor_records + strategies_to_trim))
            
            total_records = db.query(BacktestResult).count()
            if total_records - len(records_to_clean) < self.min_records_to_keep:
                records_to_clean = records_to_clean[:max(0, total_records - self.min_records_to_keep)]
            
            cleaning_stats = {
                'records_analyzed': total_records,
                'obsolete_poor_found': len(obsolete_poor_records),
                'strategy_trim_found': len(strategies_to_trim),
                'total_to_clean': len(records_to_clean),
                'records_preserved': total_records - len(records_to_clean),
                'dry_run': dry_run
            }
            
            if not dry_run and records_to_clean:
                for record in records_to_clean:
                    db.delete(record)
                
                db.commit()
                logger.info(f"Cleaned {len(records_to_clean)} obsolete records from database")
                cleaning_stats['cleaned'] = True
            else:
                cleaning_stats['cleaned'] = False
                if dry_run:
                    logger.info(f"DRY RUN: Would clean {len(records_to_clean)} records")
            
            db.close()
            return cleaning_stats
            
        except Exception as e:
            logger.error(f"Error cleaning obsolete data: {e}")
            return {'error': str(e)}
    
    def optimize_workspace(self) -> Dict:
        """
        Optimize workspace by cleaning temporary files, logs, and cache data.
        """
        optimization_stats = {
            'files_cleaned': 0,
            'space_freed_mb': 0,
            'directories_processed': []
        }
        
        try:
            temp_patterns = [
                '*.tmp', '*.temp', '*.cache', '*.log.old', '*.backup',
                '__pycache__', '*.pyc', '*.pyo'
            ]
            
            base_path = Path('/home/ubuntu/repos/Projet_AUTOBOT')
            clean_dirs = [
                base_path / 'logs',
                base_path / 'temp',
                base_path / 'cache',
                base_path / 'src',
                base_path
            ]
            
            for directory in clean_dirs:
                if directory.exists():
                    optimization_stats['directories_processed'].append(str(directory))
                    
                    for pycache_dir in directory.rglob('__pycache__'):
                        if pycache_dir.is_dir():
                            for cache_file in pycache_dir.iterdir():
                                if cache_file.is_file():
                                    size = cache_file.stat().st_size
                                    cache_file.unlink()
                                    optimization_stats['files_cleaned'] += 1
                                    optimization_stats['space_freed_mb'] += size / (1024 * 1024)
                    
                    for pattern in ['*.tmp', '*.temp', '*.cache', '*.log.old']:
                        for temp_file in directory.rglob(pattern):
                            if temp_file.is_file():
                                size = temp_file.stat().st_size
                                temp_file.unlink()
                                optimization_stats['files_cleaned'] += 1
                                optimization_stats['space_freed_mb'] += size / (1024 * 1024)
            
            if os.path.exists(self.database_path):
                original_size = os.path.getsize(self.database_path)
                
                conn = sqlite3.connect(self.database_path)
                conn.execute('VACUUM')
                conn.close()
                
                new_size = os.path.getsize(self.database_path)
                space_saved = (original_size - new_size) / (1024 * 1024)
                optimization_stats['database_optimized'] = True
                optimization_stats['database_space_saved_mb'] = round(space_saved, 2)
            
            optimization_stats['space_freed_mb'] = round(optimization_stats['space_freed_mb'], 2)
            
            logger.info(f"Workspace optimization completed: {optimization_stats['files_cleaned']} files cleaned, "
                       f"{optimization_stats['space_freed_mb']} MB freed")
            
            return optimization_stats
            
        except Exception as e:
            logger.error(f"Error optimizing workspace: {e}")
            optimization_stats['error'] = str(e)
            return optimization_stats
    
    def create_performance_summary(self) -> Dict:
        """Create a summary of preserved high-performing strategies and results."""
        try:
            db = SessionLocal()
            
            top_strategies = db.query(BacktestResult).filter(
                BacktestResult.total_return > 5.0
            ).order_by(BacktestResult.total_return.desc()).limit(20).all()
            
            all_results = db.query(BacktestResult).all()
            
            if not all_results:
                return {'error': 'No results found in database'}
            
            total_return = sum(r.total_return for r in all_results)
            avg_return = total_return / len(all_results)
            
            best_result = max(all_results, key=lambda x: x.total_return)
            worst_result = min(all_results, key=lambda x: x.total_return)
            
            strategy_performance = {}
            for result in all_results:
                if result.strategy not in strategy_performance:
                    strategy_performance[result.strategy] = {
                        'count': 0,
                        'total_return': 0,
                        'best_return': float('-inf'),
                        'worst_return': float('inf')
                    }
                
                strategy_performance[result.strategy]['count'] += 1
                strategy_performance[result.strategy]['total_return'] += result.total_return
                strategy_performance[result.strategy]['best_return'] = max(
                    strategy_performance[result.strategy]['best_return'], result.total_return
                )
                strategy_performance[result.strategy]['worst_return'] = min(
                    strategy_performance[result.strategy]['worst_return'], result.total_return
                )
            
            for strategy in strategy_performance:
                strategy_performance[strategy]['avg_return'] = (
                    strategy_performance[strategy]['total_return'] / 
                    strategy_performance[strategy]['count']
                )
            
            db.close()
            
            return {
                'total_preserved_results': len(all_results),
                'cumulative_return': round(total_return, 2),
                'average_return': round(avg_return, 2),
                'best_result': {
                    'strategy': best_result.strategy,
                    'return': round(best_result.total_return, 2),
                    'timestamp': best_result.timestamp.isoformat()
                },
                'worst_result': {
                    'strategy': worst_result.strategy,
                    'return': round(worst_result.total_return, 2),
                    'timestamp': worst_result.timestamp.isoformat()
                },
                'top_strategies': [
                    {
                        'strategy': r.strategy,
                        'return': round(r.total_return, 2),
                        'sharpe': round(r.sharpe_ratio or 0, 3),
                        'timestamp': r.timestamp.isoformat()
                    }
                    for r in top_strategies
                ],
                'strategy_performance': {
                    strategy: {
                        'count': data['count'],
                        'avg_return': round(data['avg_return'], 2),
                        'best_return': round(data['best_return'], 2),
                        'worst_return': round(data['worst_return'], 2)
                    }
                    for strategy, data in strategy_performance.items()
                }
            }
            
        except Exception as e:
            logger.error(f"Error creating performance summary: {e}")
            return {'error': str(e)}
    
    def run_full_optimization(self, dry_run: bool = False) -> Dict:
        """
        Run complete optimization process: analyze, clean, optimize, and summarize.
        
        Args:
            dry_run: If True, only analyze without making changes
        
        Returns:
            Complete optimization report
        """
        logger.info("Starting full AUTOBOT performance optimization...")
        
        health_analysis = self.analyze_database_health()
        
        cleaning_results = self.clean_obsolete_data(dry_run=dry_run)
        
        workspace_results = self.optimize_workspace() if not dry_run else {'skipped': 'dry_run'}
        
        performance_summary = self.create_performance_summary()
        
        final_health = self.analyze_database_health()
        
        optimization_report = {
            'timestamp': datetime.utcnow().isoformat(),
            'dry_run': dry_run,
            'initial_health': health_analysis,
            'cleaning_results': cleaning_results,
            'workspace_optimization': workspace_results,
            'performance_summary': performance_summary,
            'final_health': final_health,
            'improvement': {
                'health_score_change': (
                    final_health.get('health_score', 0) - 
                    health_analysis.get('health_score', 0)
                ),
                'records_optimized': cleaning_results.get('total_to_clean', 0),
                'space_freed_mb': workspace_results.get('space_freed_mb', 0)
            }
        }
        
        logger.info(f"Full optimization completed. Health score: "
                   f"{health_analysis.get('health_score', 0):.1f} → "
                   f"{final_health.get('health_score', 0):.1f}")
        
        return optimization_report

performance_optimizer = PerformanceOptimizer()
