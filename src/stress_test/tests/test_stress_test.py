import unittest
from ..core import StressTest

class TestStressTest(unittest.TestCase):
    def test_initialization(self):
        test = StressTest()
        self.assertIsNotNone(test)

    def test_run_scenario(self):
        test = StressTest()
        result = test.run_scenario()
        self.assertIn('status', result)
        self.assertEqual(result['status'], 'success')

if __name__ == '__main__':
    unittest.main()

