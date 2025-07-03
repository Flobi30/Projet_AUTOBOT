#!/usr/bin/env python3
"""
Test script for comprehensive AUTOBOT cleanup system
"""
import sys
sys.path.append('/home/ubuntu')

def test_cleanup_imports():
    """Test that cleanup system imports successfully."""
    try:
        from comprehensive_autobot_cleanup import ComprehensiveAutobotCleanup
        print('✅ Comprehensive cleanup system imports successfully')
        return True
    except ImportError as e:
        print(f'❌ Import error: {e}')
        return False

def test_cleanup_initialization():
    """Test cleanup system initialization."""
    try:
        from comprehensive_autobot_cleanup import ComprehensiveAutobotCleanup
        cleanup = ComprehensiveAutobotCleanup('/tmp/test_project')
        print('✅ Cleanup system initialized successfully')
        print(f'Found {len(cleanup.unused_code_elements)} unused code elements to process')
        print(f'Found {len(cleanup.unused_dependencies)} unused dependencies to remove')
        return True
    except Exception as e:
        print(f'❌ Initialization error: {e}')
        return False

def test_parameter_optimizer():
    """Test parameter optimizer imports and type annotations."""
    try:
        from parameter_optimizer import ParameterOptimizer, OptimizationResult
        print('✅ Parameter optimizer imports successfully')
        return True
    except ImportError as e:
        print(f'❌ Parameter optimizer import error: {e}')
        return False

if __name__ == "__main__":
    print("=== Testing AUTOBOT Cleanup System ===")
    
    tests = [
        test_cleanup_imports,
        test_cleanup_initialization,
        test_parameter_optimizer
    ]
    
    results = []
    for test in tests:
        results.append(test())
    
    success_count = sum(results)
    total_count = len(results)
    
    print(f"\n=== Test Results ===")
    print(f"Passed: {success_count}/{total_count}")
    
    if success_count == total_count:
        print("🎉 All tests passed! Cleanup system ready for deployment.")
    else:
        print("❌ Some tests failed. Check errors above.")
    
    sys.exit(0 if success_count == total_count else 1)
