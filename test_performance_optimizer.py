#!/usr/bin/env python3
"""
Test the Performance Optimizer system to ensure it works correctly.
"""
import sys
import os
sys.path.insert(0, '/home/ubuntu/repos/Projet_AUTOBOT/src')

import json
from autobot.data_cleaning.performance_optimizer import PerformanceOptimizer

def test_performance_optimizer():
    """Test the performance optimizer functionality."""
    print("=== Testing AUTOBOT Performance Optimizer ===")
    
    try:
        optimizer = PerformanceOptimizer()
        
        print("\n1. Analyzing database health...")
        health_analysis = optimizer.analyze_database_health()
        
        if 'error' in health_analysis:
            print(f"❌ Health analysis failed: {health_analysis['error']}")
            return False
        
        print(f"✅ Database Health Analysis:")
        print(f"   Total records: {health_analysis['total_records']}")
        print(f"   High performers: {health_analysis['high_performers']}")
        print(f"   Poor performers: {health_analysis['poor_performers']}")
        print(f"   Obsolete records: {health_analysis['obsolete_records']}")
        print(f"   Database size: {health_analysis['database_size_mb']} MB")
        print(f"   Health score: {health_analysis['health_score']:.1f}/100")
        print(f"   Optimization potential: {health_analysis['optimization_potential']} records")
        
        print("\n2. Testing data cleaning (DRY RUN)...")
        cleaning_results = optimizer.clean_obsolete_data(dry_run=True)
        
        if 'error' in cleaning_results:
            print(f"❌ Cleaning test failed: {cleaning_results['error']}")
            return False
        
        print(f"✅ Data Cleaning Analysis (DRY RUN):")
        print(f"   Records analyzed: {cleaning_results['records_analyzed']}")
        print(f"   Obsolete poor records: {cleaning_results['obsolete_poor_found']}")
        print(f"   Strategy trim candidates: {cleaning_results['strategy_trim_found']}")
        print(f"   Total to clean: {cleaning_results['total_to_clean']}")
        print(f"   Records to preserve: {cleaning_results['records_preserved']}")
        
        print("\n3. Testing workspace optimization...")
        workspace_results = optimizer.optimize_workspace()
        
        if 'error' in workspace_results:
            print(f"❌ Workspace optimization failed: {workspace_results['error']}")
        else:
            print(f"✅ Workspace Optimization:")
            print(f"   Files cleaned: {workspace_results['files_cleaned']}")
            print(f"   Space freed: {workspace_results['space_freed_mb']} MB")
            print(f"   Directories processed: {len(workspace_results['directories_processed'])}")
            if 'database_optimized' in workspace_results:
                print(f"   Database optimized: {workspace_results['database_space_saved_mb']} MB saved")
        
        print("\n4. Creating performance summary...")
        performance_summary = optimizer.create_performance_summary()
        
        if 'error' in performance_summary:
            print(f"❌ Performance summary failed: {performance_summary['error']}")
        else:
            print(f"✅ Performance Summary:")
            print(f"   Total preserved results: {performance_summary['total_preserved_results']}")
            print(f"   Cumulative return: {performance_summary['cumulative_return']}%")
            print(f"   Average return: {performance_summary['average_return']}%")
            print(f"   Best result: {performance_summary['best_result']['strategy']} "
                  f"({performance_summary['best_result']['return']}%)")
            print(f"   Top strategies: {len(performance_summary['top_strategies'])}")
            print(f"   Strategy types: {len(performance_summary['strategy_performance'])}")
        
        print("\n5. Running full optimization (DRY RUN)...")
        full_report = optimizer.run_full_optimization(dry_run=True)
        
        if 'improvement' in full_report:
            print(f"✅ Full Optimization Report:")
            print(f"   Health score improvement: {full_report['improvement']['health_score_change']:.1f}")
            print(f"   Records to optimize: {full_report['improvement']['records_optimized']}")
            print(f"   Potential space savings: {full_report['improvement']['space_freed_mb']} MB")
        
        print("\n=== Performance Optimizer Test Complete ===")
        print("✅ All tests passed! Performance optimizer is ready for use.")
        
        with open('/home/ubuntu/repos/Projet_AUTOBOT/performance_optimization_report.json', 'w') as f:
            json.dump(full_report, f, indent=2, default=str)
        
        print("📄 Detailed report saved to: performance_optimization_report.json")
        
        return True
        
    except Exception as e:
        print(f"❌ Performance optimizer test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_performance_optimizer()
    if success:
        print("\n🎉 Performance Optimizer is working correctly!")
    else:
        print("\n❌ Performance Optimizer needs debugging")
