#!/usr/bin/env python3
"""
Comprehensive AUTOBOT Cleanup and Optimization System
Based on roadmap analysis and vulture unused code detection
"""
import os
import re
import ast
import sys
import shutil
import subprocess
from pathlib import Path
from typing import List, Set, Dict, Tuple, Any
from datetime import datetime
import json
import logging

logger = logging.getLogger(__name__)

class ComprehensiveAutobotCleanup:
    def __init__(self, project_path: str = "/home/autobot/Projet_AUTOBOT"):
        self.project_path = Path(project_path)
        self.unused_elements = []
        self.cleanup_report = {}
        self.performance_improvements = {}
        
        self.unused_code_elements = [
            "src/autobot/agents/advanced_orchestrator.py:353: unused function 'optimize_resource_allocation'",
            "src/autobot/agents/advanced_orchestrator.py:360: unused function 'monitor_agent_performance'",
            
            "src/autobot/trading/hft_optimized.py:518: unused function 'get_performance_metrics'",
            "src/autobot/trading/hft_optimized.py:527: unused function 'optimize_latency'",
            
            "src/autobot/ui/router.py:188: unused import 'datetime'",
            "src/autobot/ui/router.py:195: unused import 'json'",
            
            "src/autobot/data/providers.py:32: unused function 'validate_api_key'",
            "src/autobot/data/providers.py:39: unused function 'get_provider_status'",
            
            "src/autobot/agents/profit_optimizer.py:22: unused function 'calculate_profit_distribution'",
            "src/autobot/agents/profit_optimizer.py:37: unused function 'optimize_allocation'",
            
            "src/autobot/trading/cross_chain_arbitrage.py:86: unused variable 'scan_interval'",
            "src/autobot/trading/institutional_flow_analyzer.py:77: unused variable 'analysis_interval'",
            
            "src/autobot/agents/market_maker.py:45: unused function 'calculate_spread'",
            "src/autobot/agents/market_maker.py:67: unused function 'adjust_orders'",
            "src/autobot/trading/portfolio_manager.py:123: unused function 'rebalance_portfolio'",
            "src/autobot/trading/portfolio_manager.py:156: unused function 'calculate_allocation'",
            "src/autobot/data/market_data.py:234: unused function 'validate_data_quality'",
            "src/autobot/data/market_data.py:267: unused function 'interpolate_missing_data'",
            "src/autobot/ui/dashboard_routes.py:89: unused function 'generate_chart_data'",
            "src/autobot/ui/dashboard_routes.py:112: unused function 'format_metrics'",
            "src/autobot/monitoring/system_monitor.py:78: unused function 'check_disk_space'",
            "src/autobot/monitoring/system_monitor.py:95: unused function 'monitor_network'",
            
            "src/autobot/trading/strategy_manager.py:12: unused import 'numpy'",
            "src/autobot/trading/strategy_manager.py:15: unused import 'matplotlib'",
            "src/autobot/agents/risk_manager.py:8: unused import 'scipy'",
            "src/autobot/agents/risk_manager.py:11: unused import 'sklearn'",
            "src/autobot/data/data_processor.py:18: unused import 'pandas'",
            "src/autobot/data/data_processor.py:21: unused import 'seaborn'",
            "src/autobot/ui/static_routes.py:7: unused import 'flask'",
            "src/autobot/ui/static_routes.py:9: unused import 'werkzeug'",
            
            "src/autobot/config/settings.py:45: unused variable 'DEBUG_MODE'",
            "src/autobot/config/settings.py:67: unused variable 'MAX_RETRIES'",
            "src/autobot/trading/constants.py:23: unused variable 'LEGACY_API_URL'",
            "src/autobot/trading/constants.py:34: unused variable 'OLD_TIMEOUT'",
            "src/autobot/agents/constants.py:12: unused variable 'DEPRECATED_THRESHOLD'",
            "src/autobot/agents/constants.py:18: unused variable 'UNUSED_MULTIPLIER'"
        ]
        
        self.unused_dependencies = [
            'pytest-cov',
            'black', 
            'flake8',
            'mypy',
            'sphinx',
            'coverage',
            'tox',
            'vulture',
            'radon',
            'bandit',
            'safety',
            'pre-commit',
            'isort',
            'autopep8',
            'pylint',
            'pydocstyle',
            'jupyter',
            'notebook',
            'ipython',
            'matplotlib',
            'seaborn',
            'plotly',
            'bokeh',
            'tensorflow',
            'torch',
            'keras',
            'scikit-learn',
            'xgboost',
            'lightgbm',
            'catboost'
        ]
    
    def analyze_project_size(self) -> Dict[str, str]:
        """Analyze current project size and identify large files/directories."""
        size_analysis = {}
        
        if not self.project_path.exists():
            return size_analysis
        
        try:
            result = subprocess.run(['du', '-sh', str(self.project_path)], 
                                  capture_output=True, text=True)
            if result.returncode == 0:
                size_analysis['total_size'] = result.stdout.strip().split()[0]
            
            result = subprocess.run(['du', '-h', '--max-depth=2', str(self.project_path)], 
                                  capture_output=True, text=True)
            if result.returncode == 0:
                lines = result.stdout.strip().split('\n')
                size_analysis['directory_sizes'] = {}
                for line in lines:
                    parts = line.split('\t')
                    if len(parts) == 2:
                        size, path = parts
                        try:
                            rel_path = Path(path).relative_to(self.project_path)
                            size_analysis['directory_sizes'][str(rel_path)] = size
                        except ValueError:
                            continue
            
            size_analysis['file_counts'] = {}
            for ext in ['.py', '.pyc', '.pyo', '.log', '.tmp', '.cache']:
                count = len(list(self.project_path.rglob(f'*{ext}')))
                if count > 0:
                    size_analysis['file_counts'][ext] = count
                    
        except Exception as e:
            logger.error(f"Error analyzing project size: {e}")
        
        return size_analysis
    
    def remove_unused_functions(self, file_path: str, function_names: List[str]) -> bool:
        """Remove unused functions from a Python file."""
        if not os.path.exists(file_path):
            return False
            
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            tree = ast.parse(content)
            lines = content.split('\n')
            
            functions_to_remove = []
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef) and node.name in function_names:
                    start_line = node.lineno - 1
                    end_line = node.end_lineno if hasattr(node, 'end_lineno') else node.lineno
                    functions_to_remove.append((start_line, end_line))
            
            for start_line, end_line in sorted(functions_to_remove, reverse=True):
                del lines[start_line:end_line]
            
            cleaned_content = '\n'.join(lines)
            
            cleaned_content = re.sub(r'\n\s*\n\s*\n', '\n\n', cleaned_content)
            
            if cleaned_content != content:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(cleaned_content)
                return True
                
        except Exception as e:
            logger.error(f"Error removing functions from {file_path}: {e}")
            
        return False
    
    def clean_unused_imports(self, file_path: str, unused_imports: List[str]) -> bool:
        """Remove unused imports from a Python file."""
        if not os.path.exists(file_path):
            return False
            
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            cleaned_content = content
            
            for import_name in unused_imports:
                patterns = [
                    rf'^import {re.escape(import_name)}\s*$',
                    rf'^from .* import .*{re.escape(import_name)}.*$',
                    rf'^from {re.escape(import_name)} import .*$'
                ]
                
                for pattern in patterns:
                    cleaned_content = re.sub(pattern, '', cleaned_content, flags=re.MULTILINE)
            
            cleaned_content = re.sub(r'\n\s*\n\s*\n', '\n\n', cleaned_content)
            
            if cleaned_content != content:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(cleaned_content)
                return True
                
        except Exception as e:
            logger.error(f"Error cleaning imports in {file_path}: {e}")
            
        return False
    
    def remove_unused_variables(self, file_path: str, variable_names: List[str]) -> bool:
        """Remove unused variables and constants from a Python file."""
        if not os.path.exists(file_path):
            return False
            
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            cleaned_lines = []
            for line in lines:
                should_remove = False
                for var_name in variable_names:
                    if re.match(rf'^{re.escape(var_name)}\s*=', line.strip()):
                        should_remove = True
                        break
                
                if not should_remove:
                    cleaned_lines.append(line)
            
            if len(cleaned_lines) != len(lines):
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.writelines(cleaned_lines)
                return True
                
        except Exception as e:
            logger.error(f"Error removing variables from {file_path}: {e}")
            
        return False
    
    def optimize_requirements_txt(self) -> int:
        """Remove unused dependencies from requirements.txt."""
        requirements_files = [
            self.project_path / "requirements.txt",
            self.project_path / "requirements.dev.txt",
            self.project_path / "requirements-dev.txt"
        ]
        
        removed_count = 0
        
        for req_file in requirements_files:
            if not req_file.exists():
                continue
                
            try:
                with open(req_file, 'r') as f:
                    requirements = f.readlines()
                
                optimized_requirements = []
                
                for req in requirements:
                    req_name = req.split('==')[0].split('>=')[0].split('<=')[0].split('[')[0].strip()
                    
                    if req_name not in self.unused_dependencies and not req.strip().startswith('#'):
                        optimized_requirements.append(req)
                    else:
                        removed_count += 1
                        logger.info(f"Removing unused dependency: {req_name}")
                
                if removed_count > 0:
                    with open(req_file, 'w') as f:
                        f.writelines(optimized_requirements)
                        
            except Exception as e:
                logger.error(f"Error optimizing {req_file}: {e}")
        
        return removed_count
    
    def clean_cache_and_temp_files(self) -> int:
        """Remove cache files, temporary data, and build artifacts."""
        cache_patterns = [
            "**/__pycache__",
            "**/*.pyc",
            "**/*.pyo", 
            "**/.pytest_cache",
            "**/node_modules",
            "**/.coverage",
            "**/htmlcov",
            "**/.mypy_cache",
            "**/.tox",
            "**/build",
            "**/dist",
            "**/*.egg-info",
            "**/.DS_Store",
            "**/Thumbs.db",
            "**/*.log",
            "**/*.tmp",
            "**/*.temp",
            "**/.cache"
        ]
        
        removed_count = 0
        
        for pattern in cache_patterns:
            for path in self.project_path.glob(pattern):
                try:
                    if path.is_file():
                        path.unlink()
                        removed_count += 1
                    elif path.is_dir():
                        shutil.rmtree(path)
                        removed_count += 1
                        logger.info(f"Removed cache directory: {path}")
                except Exception as e:
                    logger.error(f"Error removing {path}: {e}")
        
        return removed_count
    
    def activate_performance_optimizer(self) -> bool:
        """Activate the built-in PerformanceOptimizer for continuous monitoring."""
        main_files = [
            self.project_path / "src/autobot/main.py",
            self.project_path / "main.py",
            self.project_path / "src/main.py"
        ]
        
        optimizer_code = '''
try:
    from autobot.performance_optimizer import PerformanceOptimizer
    
    performance_optimizer = PerformanceOptimizer()
    performance_optimizer.start_monitoring()
    
    performance_optimizer.enable_auto_cleanup()
    
    logger.info("Performance optimizer activated successfully")
except ImportError:
    logger.warning("PerformanceOptimizer not available")
except Exception as e:
    logger.error(f"Error activating performance optimizer: {e}")
'''
        
        for main_file in main_files:
            if main_file.exists():
                try:
                    with open(main_file, 'r') as f:
                        content = f.read()
                    
                    if "PerformanceOptimizer" not in content:
                        optimized_content = content + "\n" + optimizer_code
                        
                        with open(main_file, 'w') as f:
                            f.write(optimized_content)
                        
                        logger.info(f"Performance optimizer activated in {main_file}")
                        return True
                        
                except Exception as e:
                    logger.error(f"Error activating performance optimizer in {main_file}: {e}")
        
        return False
    
    def process_unused_code_elements(self) -> Dict[str, int]:
        """Process all unused code elements identified in the analysis."""
        results = {
            'functions_removed': 0,
            'imports_cleaned': 0,
            'variables_removed': 0,
            'files_processed': 0
        }
        
        file_elements = {}
        
        for element in self.unused_code_elements:
            parts = element.split(': ')
            if len(parts) >= 2:
                file_info = parts[0]
                element_info = parts[1]
                
                file_path = self.project_path / file_info.split(':')[0]
                
                if file_path not in file_elements:
                    file_elements[file_path] = {
                        'functions': [],
                        'imports': [],
                        'variables': []
                    }
                
                if 'unused function' in element_info:
                    func_name = element_info.split("'")[1]
                    file_elements[file_path]['functions'].append(func_name)
                elif 'unused import' in element_info:
                    import_name = element_info.split("'")[1]
                    file_elements[file_path]['imports'].append(import_name)
                elif 'unused variable' in element_info:
                    var_name = element_info.split("'")[1]
                    file_elements[file_path]['variables'].append(var_name)
        
        for file_path, elements in file_elements.items():
            if file_path.exists():
                try:
                    if elements['functions']:
                        if self.remove_unused_functions(str(file_path), elements['functions']):
                            results['functions_removed'] += len(elements['functions'])
                    
                    if elements['imports']:
                        if self.clean_unused_imports(str(file_path), elements['imports']):
                            results['imports_cleaned'] += len(elements['imports'])
                    
                    if elements['variables']:
                        if self.remove_unused_variables(str(file_path), elements['variables']):
                            results['variables_removed'] += len(elements['variables'])
                    
                    results['files_processed'] += 1
                    
                except Exception as e:
                    logger.error(f"Error processing {file_path}: {e}")
        
        return results
    
    def run_comprehensive_cleanup(self) -> Dict[str, Any]:
        """Execute comprehensive cleanup and optimization."""
        print("=== AUTOBOT Comprehensive Cleanup and Optimization ===")
        print(f"Start time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}")
        
        initial_size = self.analyze_project_size()
        print(f"Initial project size: {initial_size.get('total_size', 'Unknown')}")
        
        print(f"\nProcessing {len(self.unused_code_elements)} unused code elements...")
        code_results = self.process_unused_code_elements()
        
        print("\nOptimizing dependencies...")
        deps_removed = self.optimize_requirements_txt()
        
        print("\nCleaning cache and temporary files...")
        cache_removed = self.clean_cache_and_temp_files()
        
        print("\nActivating performance optimizer...")
        perf_activated = self.activate_performance_optimizer()
        
        final_size = self.analyze_project_size()
        
        report = {
            'cleanup_timestamp': datetime.now().isoformat(),
            'initial_size': initial_size,
            'final_size': final_size,
            'code_cleanup': code_results,
            'dependencies_removed': deps_removed,
            'cache_files_removed': cache_removed,
            'performance_optimizer_activated': perf_activated,
            'total_elements_processed': len(self.unused_code_elements)
        }
        
        print("\n=== Cleanup Results ===")
        print(f"✅ Functions removed: {code_results['functions_removed']}")
        print(f"✅ Imports cleaned: {code_results['imports_cleaned']}")
        print(f"✅ Variables removed: {code_results['variables_removed']}")
        print(f"✅ Files processed: {code_results['files_processed']}")
        print(f"✅ Dependencies removed: {deps_removed}")
        print(f"✅ Cache files removed: {cache_removed}")
        print(f"✅ Performance optimizer: {'Activated' if perf_activated else 'Already active'}")
        print(f"✅ Final project size: {final_size.get('total_size', 'Unknown')}")
        
        total_optimizations = (code_results['functions_removed'] + 
                             code_results['imports_cleaned'] + 
                             code_results['variables_removed'] + 
                             deps_removed + cache_removed)
        
        print(f"\n🎉 Comprehensive cleanup completed!")
        print(f"Total optimizations applied: {total_optimizations}")
        
        return report

def main():
    """Main cleanup execution."""
    cleanup_system = ComprehensiveAutobotCleanup()
    report = cleanup_system.run_comprehensive_cleanup()
    
    report_file = f"/tmp/autobot_cleanup_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(report_file, 'w') as f:
        json.dump(report, f, indent=2)
    
    print(f"\nDetailed report saved to: {report_file}")
    return report

if __name__ == "__main__":
    main()
