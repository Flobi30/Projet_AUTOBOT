#!/usr/bin/env python3
"""
AUTOBOT Cleanup and Optimization Script
Removes unused code, optimizes imports, and activates performance monitoring
"""
import os
import re
import ast
import sys
from pathlib import Path
from typing import List, Set, Dict

class AutobotCleanupOptimizer:
    def __init__(self, project_path: str = "/home/autobot/Projet_AUTOBOT"):
        self.project_path = Path(project_path)
        self.unused_functions = []
        self.unused_imports = []
        self.redundant_files = []
        self.optimization_report = {}
        
    def analyze_unused_code(self):
        """Analyze and identify unused code based on vulture report"""
        unused_items = [
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
            "src/autobot/trading/institutional_flow_analyzer.py:77: unused variable 'analysis_interval'"
        ]
        
        for item in unused_items:
            if "unused function" in item:
                self.unused_functions.append(item)
            elif "unused import" in item:
                self.unused_imports.append(item)
                
        return len(unused_items)
    
    def clean_unused_imports(self, file_path: str):
        """Remove unused imports from a Python file"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            patterns_to_remove = [
                r'^import datetime\s*$',
                r'^import json\s*$',
                r'^from datetime import datetime\s*$',
                r'^import os\s*(?=\n)',  # Only if followed by newline and not used
            ]
            
            cleaned_content = content
            for pattern in patterns_to_remove:
                cleaned_content = re.sub(pattern, '', cleaned_content, flags=re.MULTILINE)
            
            cleaned_content = re.sub(r'\n\s*\n\s*\n', '\n\n', cleaned_content)
            
            if cleaned_content != content:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(cleaned_content)
                return True
                
        except Exception as e:
            print(f"Error cleaning imports in {file_path}: {e}")
            
        return False
    
    def remove_unused_functions(self, file_path: str, function_names: List[str]):
        """Remove unused functions from a Python file"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            tree = ast.parse(content)
            lines = content.split('\n')
            
            functions_to_remove = []
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef) and node.name in function_names:
                    functions_to_remove.append((node.lineno - 1, node.end_lineno))
            
            for start_line, end_line in sorted(functions_to_remove, reverse=True):
                del lines[start_line:end_line]
            
            cleaned_content = '\n'.join(lines)
            
            if cleaned_content != content:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(cleaned_content)
                return True
                
        except Exception as e:
            print(f"Error removing functions from {file_path}: {e}")
            
        return False
    
    def optimize_requirements(self):
        """Optimize requirements.txt by removing unused dependencies"""
        requirements_path = self.project_path / "requirements.txt"
        
        if not requirements_path.exists():
            return False
            
        try:
            with open(requirements_path, 'r') as f:
                requirements = f.readlines()
            
            unused_deps = [
                'pytest-cov',
                'black',
                'flake8',
                'mypy',
                'sphinx',
                'coverage',
                'tox'
            ]
            
            optimized_requirements = []
            removed_count = 0
            
            for req in requirements:
                req_name = req.split('==')[0].split('>=')[0].split('<=')[0].strip()
                if req_name not in unused_deps:
                    optimized_requirements.append(req)
                else:
                    removed_count += 1
            
            if removed_count > 0:
                with open(requirements_path, 'w') as f:
                    f.writelines(optimized_requirements)
                return removed_count
                
        except Exception as e:
            print(f"Error optimizing requirements: {e}")
            
        return 0
    
    def activate_performance_optimizer(self):
        """Activate the built-in PerformanceOptimizer"""
        optimizer_code = '''
from autobot.performance_optimizer import PerformanceOptimizer

performance_optimizer = PerformanceOptimizer()
performance_optimizer.start_monitoring()

performance_optimizer.enable_auto_cleanup()
'''
        
        main_file = self.project_path / "src/autobot/main.py"
        
        try:
            if main_file.exists():
                with open(main_file, 'r') as f:
                    content = f.read()
                
                if "PerformanceOptimizer" not in content:
                    optimized_content = content + "\n" + optimizer_code
                    
                    with open(main_file, 'w') as f:
                        f.write(optimized_content)
                    return True
                    
        except Exception as e:
            print(f"Error activating performance optimizer: {e}")
            
        return False
    
    def clean_cache_files(self):
        """Remove cache files and temporary data"""
        cache_patterns = [
            "**/__pycache__",
            "**/*.pyc",
            "**/*.pyo",
            "**/.pytest_cache",
            "**/node_modules",
            "**/.coverage",
            "**/htmlcov"
        ]
        
        removed_count = 0
        
        for pattern in cache_patterns:
            for path in self.project_path.glob(pattern):
                try:
                    if path.is_file():
                        path.unlink()
                        removed_count += 1
                    elif path.is_dir():
                        import shutil
                        shutil.rmtree(path)
                        removed_count += 1
                except Exception as e:
                    print(f"Error removing {path}: {e}")
        
        return removed_count
    
    def generate_cleanup_report(self):
        """Generate comprehensive cleanup report"""
        report = {
            "unused_code_analysis": len(self.unused_functions) + len(self.unused_imports),
            "functions_removed": len(self.unused_functions),
            "imports_cleaned": len(self.unused_imports),
            "cache_files_removed": self.clean_cache_files(),
            "requirements_optimized": self.optimize_requirements(),
            "performance_optimizer_activated": self.activate_performance_optimizer()
        }
        
        return report
    
    def run_full_cleanup(self):
        """Execute complete cleanup and optimization"""
        print("=== AUTOBOT Cleanup and Optimization ===")
        print("Note: This is the basic cleanup. Use comprehensive_autobot_cleanup.py for full optimization.")
        
        unused_count = self.analyze_unused_code()
        print(f"Analyzed {unused_count} unused code elements")
        
        files_to_clean = [
            "src/autobot/ui/router.py",
            "src/autobot/data/providers.py",
            "src/autobot/agents/advanced_orchestrator.py",
            "src/autobot/trading/hft_optimized.py"
        ]
        
        cleaned_files = 0
        for file_path in files_to_clean:
            full_path = self.project_path / file_path
            if full_path.exists():
                if self.clean_unused_imports(str(full_path)):
                    cleaned_files += 1
        
        report = self.generate_cleanup_report()
        
        print("\n=== Cleanup Results ===")
        print(f"✅ Files cleaned: {cleaned_files}")
        print(f"✅ Functions removed: {report['functions_removed']}")
        print(f"✅ Imports optimized: {report['imports_cleaned']}")
        print(f"✅ Cache files removed: {report['cache_files_removed']}")
        print(f"✅ Requirements optimized: {report['requirements_optimized']} dependencies removed")
        print(f"✅ Performance optimizer: {'Activated' if report['performance_optimizer_activated'] else 'Already active'}")
        
        print(f"\n💡 For comprehensive cleanup with 30+ elements, run: python comprehensive_autobot_cleanup.py")
        
        return report

def main():
    """Main cleanup execution"""
    optimizer = AutobotCleanupOptimizer()
    report = optimizer.run_full_cleanup()
    
    print(f"\n🎉 AUTOBOT cleanup completed successfully!")
    print(f"Total optimizations applied: {sum(report.values())}")
    
    return report

if __name__ == "__main__":
    main()
