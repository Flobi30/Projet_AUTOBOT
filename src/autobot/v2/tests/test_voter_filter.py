import unittest
import logging
from datetime import datetime, timezone

import pytest

from autobot.v2.modules.multi_indicator_vote import MultiIndicatorVoter, VOTE_BUY, VOTE_SELL, VOTE_NEUTRAL

pytestmark = pytest.mark.unit

class TestVoterFilter(unittest.TestCase):
    def setUp(self):
        # min_votes=2 pour simplifier le test
        self.voter = MultiIndicatorVoter(min_votes_required=2, unanimity_threshold=0.7)
        self.voter.register_indicator("xgboost", weight=1.2)
        self.voter.register_indicator("heuristic", weight=1.0)
        self.voter.register_indicator("sentiment", weight=0.8)

    def test_strong_sell_consensus_blocks_buy(self):
        """Si consensus STRONG SELL, on doit bloquer l'achat."""
        self.voter.submit_vote("xgboost", VOTE_SELL, confidence=0.9)
        self.voter.submit_vote("heuristic", VOTE_SELL, confidence=0.8)
        self.voter.submit_vote("sentiment", VOTE_SELL, confidence=0.7)
        
        tally = self.voter.tally()
        self.assertEqual(tally["signal"], VOTE_SELL)
        self.assertEqual(tally["strength"], "strong")
        
        # Logique de filtrage que nous allons implémenter dans GridStrategyAsync
        should_skip_buy = (tally["signal"] == VOTE_SELL and tally["strength"] == "strong")
        self.assertTrue(should_skip_buy, "L'achat devrait être bloqué par un consensus SELL fort")

    def test_weak_sell_consensus_does_not_block_buy(self):
        """Si consensus SELL faible, on ne bloque pas forcément (selon politique)."""
        self.voter.submit_vote("xgboost", VOTE_SELL, confidence=0.6)
        self.voter.submit_vote("heuristic", VOTE_BUY, confidence=0.5)
        self.voter.submit_vote("sentiment", VOTE_NEUTRAL, confidence=1.0)
        
        tally = self.voter.tally()
        # Ici la force devrait être "weak"
        self.assertEqual(tally["strength"], "weak")
        
        should_skip_buy = (tally["signal"] == VOTE_SELL and tally["strength"] == "strong")
        self.assertFalse(should_skip_buy, "L'achat ne devrait pas être bloqué par un consensus faible")

    def test_strong_buy_consensus_allows_buy(self):
        """Si consensus STRONG BUY, l'achat est autorisé."""
        self.voter.submit_vote("xgboost", VOTE_BUY, confidence=0.9)
        self.voter.submit_vote("heuristic", VOTE_BUY, confidence=0.8)
        
        tally = self.voter.tally()
        self.assertEqual(tally["signal"], VOTE_BUY)
        
        should_skip_buy = (tally["signal"] == VOTE_SELL and tally["strength"] == "strong")
        self.assertFalse(should_skip_buy, "L'achat ne devrait pas être bloqué par un consensus BUY")

if __name__ == "__main__":
    unittest.main()
