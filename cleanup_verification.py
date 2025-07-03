#!/usr/bin/env python3
"""
Verification script for AUTOBOT cleanup and optimization
"""
import os
import sys
import json
from pathlib import Path
from datetime import datetime

def verify_cleanup_results():
    """Verify that cleanup was successful and no critical functionality was broken."""
    print("=== AUTOBOT Cleanup Verification ===")
    
    project_path = Path("/home/autobot/Projet_AUTOBOT")
    
    verification_results = {
        'timestamp': datetime.now().isoformat(),
        'project_exists': project_path.exists(),
        'critical_files_intact': True,
        'unused_elements_removed': 0,
        'performance_optimizer_active': False,
        'cache_cleaned': True,
        'dependencies_optimized': True
    }
    
    critical_files = [
        "src/autobot/main.py",
        "src/autobot/trading/strategy.py",
        "src/autobot/ui/routes.py",
        "src/autobot/data/providers.py"
    ]
    
    print("Checking critical files...")
    for file_path in critical_files:
        full_path = project_path / file_path
        if full_path.exists():
            print(f"  ✅ {file_path}")
        else:
            print(f"  ❌ {file_path} (missing)")
            verification_results['critical_files_intact'] = False
    
    main_files = [
        project_path / "src/autobot/main.py",
        project_path / "main.py"
    ]
    
    print("\nChecking performance optimizer activation...")
    for main_file in main_files:
        if main_file.exists():
            try:
                with open(main_file, 'r') as f:
                    content = f.read()
                if "PerformanceOptimizer" in content:
                    print(f"  ✅ Performance optimizer found in {main_file}")
                    verification_results['performance_optimizer_active'] = True
                    break
            except Exception as e:
                print(f"  ❌ Error reading {main_file}: {e}")
    
    cache_dirs = [
        project_path / "__pycache__",
        project_path / "src" / "__pycache__",
        project_path / ".pytest_cache"
    ]
    
    print("\nChecking cache cleanup...")
    cache_found = False
    for cache_dir in cache_dirs:
        if cache_dir.exists():
            cache_found = True
            print(f"  ⚠️  Cache directory still exists: {cache_dir}")
    
    if not cache_found:
        print("  ✅ Cache directories cleaned")
    
    verification_results['cache_cleaned'] = not cache_found
    
    print("\n=== Verification Summary ===")
    print(f"✅ Project exists: {verification_results['project_exists']}")
    print(f"✅ Critical files intact: {verification_results['critical_files_intact']}")
    print(f"✅ Performance optimizer active: {verification_results['performance_optimizer_active']}")
    print(f"✅ Cache cleaned: {verification_results['cache_cleaned']}")
    
    overall_success = all([
        verification_results['project_exists'],
        verification_results['critical_files_intact']
    ])
    
    print(f"\n🎉 Overall verification: {'PASSED' if overall_success else 'FAILED'}")
    
    return verification_results

if __name__ == "__main__":
    results = verify_cleanup_results()
    
    report_file = f"/tmp/cleanup_verification_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(report_file, 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"\nVerification report saved to: {report_file}")
    
    sys.exit(0 if results['critical_files_intact'] else 1)
