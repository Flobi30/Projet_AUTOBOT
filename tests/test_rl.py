
import unittest
from autobot.rl import RLModule

class TestRLModule(unittest.TestCase):
    def test_greet(self):
        module = RLModule('Autobot')
        self.assertEqual(module.greet(), "Welcome to the Autobot Reinforcement Learning Module")

if __name__ == "__main__":
    unittest.main()


