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
        self.license_manager.verify_license.return_value = True
        self.license_manager.get_max_instances.return_value = 10
        
        self.thread_manager = GhostingThreadManager()
    
    def tearDown(self):
        """
        Tear down test fixtures.
        """
        self.thread_manager.stop_all_threads()
    
    def test_create_heartbeat_thread(self):
        """
        Test creating a heartbeat thread.
        """
        target_mock = MagicMock()
        
        thread = self.thread_manager.create_heartbeat_thread(
            target=target_mock,
            name="test_heartbeat"
        )
        
        self.assertTrue(thread.is_alive())
        self.assertEqual(thread.name, "test_heartbeat")
        
        time.sleep(0.1)
        
        thread.stop()
        
        time.sleep(0.1)
        
        self.assertFalse(thread.is_alive())
    
    def test_create_cleanup_thread(self):
        """
        Test creating a cleanup thread.
        """
        target_mock = MagicMock()
        
        thread = self.thread_manager.create_cleanup_thread(
            target=target_mock,
            name="test_cleanup"
        )
        
        self.assertTrue(thread.is_alive())
        self.assertEqual(thread.name, "test_cleanup")
        
        time.sleep(0.1)
        
        thread.stop()
        
        time.sleep(0.1)
        
        self.assertFalse(thread.is_alive())
    
    def test_create_worker_thread(self):
        """
        Test creating a worker thread.
        """
        target_mock = MagicMock()
        
        thread = self.thread_manager.create_worker_thread(
            target=target_mock,
            name="test_worker",
            args=(1, 2, 3)
        )
        
        self.assertTrue(thread.is_alive())
        self.assertEqual(thread.name, "test_worker")
        
        time.sleep(0.1)
        
        thread.stop()
        
        time.sleep(0.1)
        
        self.assertFalse(thread.is_alive())
        target_mock.assert_called_with(1, 2, 3)
    
    def test_stop_all_threads(self):
        """
        Test stopping all threads.
        """
        target_mock1 = MagicMock()
        target_mock2 = MagicMock()
        target_mock3 = MagicMock()
        
        thread1 = self.thread_manager.create_heartbeat_thread(
            target=target_mock1,
            name="test_heartbeat"
        )
        
        thread2 = self.thread_manager.create_cleanup_thread(
            target=target_mock2,
            name="test_cleanup"
        )
        
        thread3 = self.thread_manager.create_worker_thread(
            target=target_mock3,
            name="test_worker"
        )
        
        self.assertTrue(thread1.is_alive())
        self.assertTrue(thread2.is_alive())
        self.assertTrue(thread3.is_alive())
        
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
        target_mock = MagicMock()
        
        thread = self.thread_manager.create_heartbeat_thread(
            target=target_mock,
            name="test_heartbeat"
        )
        
        stats = self.thread_manager.get_thread_stats()
        
        self.assertEqual(stats["total_threads"], 1)
        self.assertEqual(stats["active_threads"], 1)
        self.assertTrue("test_heartbeat" in stats["threads"])
        self.assertTrue(stats["threads"]["test_heartbeat"]["alive"])
        
        thread.stop()
        
        time.sleep(0.1)
        
        stats = self.thread_manager.get_thread_stats()
        self.assertEqual(stats["total_threads"], 1)
        self.assertEqual(stats["active_threads"], 0)

if __name__ == "__main__":
    unittest.main()
