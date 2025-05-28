"""
Test module for ghosting thread management integration.

This module tests the integration between the thread management system and
the ghosting manager to ensure proper thread cleanup during CI.
"""

import os
import sys
import unittest
import threading
import time
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

from autobot.autobot_security.license_manager import LicenseManager
from autobot.trading.ghosting_manager import GhostingManager, GhostingMode
from autobot.trading.ghosting_manager_thread_integration import GhostingThreadManager
from autobot.thread_management import is_shutdown_requested, create_managed_thread

class TestGhostingThreadManagement(unittest.TestCase):
    """
    Test case for ghosting thread management integration.
    """
    
    def setUp(self):
        """
        Set up test fixtures.
        """
        self.license_manager = MagicMock(spec=LicenseManager)
        self.license_manager._verify_license.return_value = True  # Mock the private method correctly
        self.license_manager.get_license_info.return_value = {
            "max_instances": 10,
            "features": {
                "ghosting": {
                    "max_usage": 10,
                    "enabled": True
                }
            }
        }
        self.license_manager.is_feature_enabled.return_value = True
        self.license_manager.use_feature.return_value = True
        
        self.thread_manager = GhostingThreadManager()
        self.running_flags = {}
    
    def tearDown(self):
        """
        Tear down test fixtures.
        """
        for flag_name in self.running_flags:
            self.running_flags[flag_name] = False
            
        self.thread_manager.stop_all_threads()
        
        time.sleep(0.2)
    
    def _create_target_function(self, flag_name, should_exit=False):
        """
        Create a target function that runs until the flag is set to False.
        
        Args:
            flag_name: Name of the flag to check
            should_exit: Whether the function should exit immediately (for testing)
            
        Returns:
            Function: Target function for thread
        """
        self.running_flags[flag_name] = True
        
        def target_function(*args, **kwargs):
            if should_exit:
                return
                
            while self.running_flags[flag_name] and not is_shutdown_requested():
                time.sleep(0.01)
                
            return args
        
        return target_function
    
    def test_create_heartbeat_thread(self):
        """
        Test creating a heartbeat thread.
        """
        target_function = self._create_target_function("heartbeat")
        
        thread = self.thread_manager.create_heartbeat_thread(
            target=target_function,
            name="test_heartbeat"
        )
        
        time.sleep(0.1)
        
        self.assertTrue(thread.is_alive())
        self.assertEqual(thread.name, "test_heartbeat")
        
        self.running_flags["heartbeat"] = False
        thread.stop()
        
        time.sleep(0.1)
        
        self.assertFalse(thread.is_alive())
    
    def test_create_cleanup_thread(self):
        """
        Test creating a cleanup thread.
        """
        target_function = self._create_target_function("cleanup")
        
        thread = self.thread_manager.create_cleanup_thread(
            target=target_function,
            name="test_cleanup"
        )
        
        time.sleep(0.1)
        
        self.assertTrue(thread.is_alive())
        self.assertEqual(thread.name, "test_cleanup")
        
        self.running_flags["cleanup"] = False
        thread.stop()
        
        time.sleep(0.1)
        
        self.assertFalse(thread.is_alive())
    
    def test_create_worker_thread(self):
        """
        Test creating a worker thread.
        """
        target_function = self._create_target_function("worker")
        
        thread = self.thread_manager.create_worker_thread(
            target=target_function,
            name="test_worker",
            args=(1, 2, 3)
        )
        
        time.sleep(0.1)
        
        self.assertTrue(thread.is_alive())
        self.assertEqual(thread.name, "test_worker")
        
        self.running_flags["worker"] = False
        thread.stop()
        
        time.sleep(0.1)
        
        self.assertFalse(thread.is_alive())
    
    def test_stop_all_threads(self):
        """
        Test stopping all threads.
        """
        target_function1 = self._create_target_function("heartbeat2")
        target_function2 = self._create_target_function("cleanup2")
        target_function3 = self._create_target_function("worker2")
        
        thread1 = self.thread_manager.create_heartbeat_thread(
            target=target_function1,
            name="test_heartbeat"
        )
        
        thread2 = self.thread_manager.create_cleanup_thread(
            target=target_function2,
            name="test_cleanup"
        )
        
        thread3 = self.thread_manager.create_worker_thread(
            target=target_function3,
            name="test_worker"
        )
        
        time.sleep(0.1)
        
        self.assertTrue(thread1.is_alive())
        self.assertTrue(thread2.is_alive())
        self.assertTrue(thread3.is_alive())
        
        self.running_flags["heartbeat2"] = False
        self.running_flags["cleanup2"] = False
        self.running_flags["worker2"] = False
        
        time.sleep(0.1)
        
        results = self.thread_manager.stop_all_threads()
        
        time.sleep(0.1)
        
        self.assertFalse(thread1.is_alive())
        self.assertFalse(thread2.is_alive())
        self.assertFalse(thread3.is_alive())
        
        self.assertEqual(len(results), 3)
        self.assertTrue(results["test_heartbeat"])
        self.assertTrue(results["test_cleanup"])
        self.assertTrue(results["test_worker"])
    
    def test_get_thread_stats(self):
        """
        Test getting thread statistics.
        """
        target_function = self._create_target_function("heartbeat_stats")
        
        thread = self.thread_manager.create_heartbeat_thread(
            target=target_function,
            name="test_heartbeat"
        )
        
        time.sleep(0.1)
        
        stats = self.thread_manager.get_thread_stats()
        
        self.assertEqual(stats["total_threads"], 1)
        self.assertEqual(stats["active_threads"], 1)
        self.assertTrue("test_heartbeat" in stats["threads"])
        self.assertTrue(stats["threads"]["test_heartbeat"]["alive"])
        
        self.running_flags["heartbeat_stats"] = False
        thread.stop()
        
        time.sleep(0.1)
        
        stats = self.thread_manager.get_thread_stats()
        self.assertEqual(stats["total_threads"], 1)
        self.assertEqual(stats["active_threads"], 0)

if __name__ == "__main__":
    unittest.main()
