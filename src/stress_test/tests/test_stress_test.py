Write-Output "##active_line10##"
import unittest
Write-Output "##active_line11##"
from stress_test.core import StressTest
Write-Output "##active_line12##"
Write-Output "##active_line13##"
class TestStressTest(unittest.TestCase):
Write-Output "##active_line14##"
    def test_initialization(self):
Write-Output "##active_line15##"
        test = StressTest()
Write-Output "##active_line16##"
        self.assertIsNotNone(test)
Write-Output "##active_line17##"
Write-Output "##active_line18##"
    def test_run_scenario(self):
Write-Output "##active_line19##"
        test = StressTest()
Write-Output "##active_line20##"
        result = test.run_scenario()
Write-Output "##active_line21##"
        self.assertIn('status', result)
Write-Output "##active_line22##"
        self.assertEqual(result['status'], 'success')
Write-Output "##active_line23##"
Write-Output "##active_line24##"
if __name__ == '__main__':
Write-Output "##active_line25##"
    unittest.main()
Write-Output "##active_line26##"

