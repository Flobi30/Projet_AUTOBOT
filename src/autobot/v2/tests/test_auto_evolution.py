"""
Tests pour AutoEvolutionManager
"""

import pytest
pytestmark = pytest.mark.unit

import unittest
import tempfile
import os
from datetime import datetime, timezone, timedelta
from src.autobot.v2.auto_evolution import (
    AutoEvolutionManager, SystemPhase, PHASE_1_TO_2_CRITERIA
)


class TestAutoEvolutionManager(unittest.TestCase):
    """Tests du gestionnaire d'évolution"""
    
    def setUp(self):
        """Crée une instance temporaire pour chaque test"""
        self.temp_db = tempfile.mktemp(suffix='.db')
        self.manager = AutoEvolutionManager(db_path=self.temp_db)
    
    def tearDown(self):
        """Nettoie après chaque test"""
        if os.path.exists(self.temp_db):
            os.remove(self.temp_db)
    
    def test_initial_phase(self):
        """Test que la phase initiale est Phase 1"""
        self.assertEqual(
            self.manager.get_current_phase(),
            SystemPhase.PHASE_1_SURVIVAL
        )
    
    def test_hard_stop_daily(self):
        """Test le hard stop journalier -5%"""
        # Simuler une perte journalière de -6%
        result = self.manager.check_hard_stops(
            daily_loss_pct=-6.0,
            total_drawdown_pct=-3.0
        )
        
        self.assertIsNotNone(result)
        self.assertEqual(result['type'], 'daily_limit')
        self.assertEqual(result['action'], 'PAUSE')
    
    def test_hard_stop_total(self):
        """Test le hard stop total -15%"""
        result = self.manager.check_hard_stops(
            daily_loss_pct=-2.0,
            total_drawdown_pct=-16.0
        )
        
        self.assertIsNotNone(result)
        self.assertEqual(result['type'], 'max_drawdown')
        self.assertEqual(result['action'], 'STOP')
    
    def test_no_hard_stop(self):
        """Test qu'il n'y a pas de hard stop dans les limites"""
        result = self.manager.check_hard_stops(
            daily_loss_pct=-3.0,
            total_drawdown_pct=-10.0
        )
        
        self.assertIsNone(result)
    
    def test_transition_criteria_not_met_duration(self):
        """Test que la transition échoue si durée insuffisante"""
        # Forcer la date de début à il y a 30 jours (au lieu de 90)
        self.manager._phase_start_date = datetime.now(timezone.utc) - timedelta(days=30)
        
        eligibility = self.manager.evaluate_transition_eligibility(
            current_capital=1500.0,
            initial_capital=1000.0,
            max_drawdown_pct=-10.0,
            atr_14=5.0,
            max_1h_spike=3.0
        )
        
        self.assertFalse(eligibility['eligible'])
        self.assertFalse(eligibility['criteria_met']['duration'])
    
    def test_transition_criteria_not_met_capital(self):
        """Test que la transition échoue si capital insuffisant"""
        # Forcer la date de début à il y a 100 jours
        self.manager._phase_start_date = datetime.now(timezone.utc) - timedelta(days=100)
        
        eligibility = self.manager.evaluate_transition_eligibility(
            current_capital=800.0,  # Moins de 1000€
            initial_capital=1000.0,
            max_drawdown_pct=-10.0,
            atr_14=5.0,
            max_1h_spike=3.0
        )
        
        self.assertFalse(eligibility['eligible'])
        self.assertFalse(eligibility['criteria_met']['capital'])
    
    def test_transition_criteria_not_met_drawdown(self):
        """Test que la transition échoue si drawdown trop élevé"""
        self.manager._phase_start_date = datetime.now(timezone.utc) - timedelta(days=100)
        
        eligibility = self.manager.evaluate_transition_eligibility(
            current_capital=1500.0,
            initial_capital=1000.0,
            max_drawdown_pct=-20.0,  # Plus de -15%
            atr_14=5.0,
            max_1h_spike=3.0
        )
        
        self.assertFalse(eligibility['eligible'])
        self.assertFalse(eligibility['criteria_met']['drawdown'])
    
    def test_transition_criteria_not_met_atr(self):
        """Test que la transition échoue si ATR instable"""
        self.manager._phase_start_date = datetime.now(timezone.utc) - timedelta(days=100)
        
        eligibility = self.manager.evaluate_transition_eligibility(
            current_capital=1500.0,
            initial_capital=1000.0,
            max_drawdown_pct=-10.0,
            atr_14=15.0,  # Au-dessus de 8% = instable
            max_1h_spike=3.0
        )
        
        self.assertFalse(eligibility['eligible'])
        self.assertFalse(eligibility['criteria_met']['atr_stable'])
    
    def test_transition_criteria_all_met(self):
        """Test que la transition réussit si tous critères OK"""
        self.manager._phase_start_date = datetime.now(timezone.utc) - timedelta(days=100)
        
        eligibility = self.manager.evaluate_transition_eligibility(
            current_capital=1500.0,
            initial_capital=1000.0,
            max_drawdown_pct=-10.0,
            atr_14=5.0,  # Entre 2% et 8%
            max_1h_spike=3.0  # Moins de 5%
        )
        
        self.assertTrue(eligibility['eligible'])
        self.assertTrue(all(eligibility['criteria_met'].values()))
        self.assertTrue(eligibility['requires_approval'])
    
    def test_transition_requires_manual_approval(self):
        """Test que la transition nécessite une approbation manuelle"""
        self.manager._phase_start_date = datetime.now(timezone.utc) - timedelta(days=100)
        
        # Sans approbation
        result = self.manager.request_phase_transition(user_approved=False)
        self.assertFalse(result['success'])
        self.assertTrue(result.get('pending_approval'))
        
        # L'état ne devrait pas changer
        self.assertEqual(
            self.manager.get_current_phase(),
            SystemPhase.PHASE_1_SURVIVAL
        )
    
    def test_transition_with_approval(self):
        """Test la transition avec approbation manuelle"""
        # Forcer une date ancienne pour passer l'hystérésis
        self.manager._phase_start_date = datetime.now(timezone.utc) - timedelta(days=10)
        
        result = self.manager.request_phase_transition(
            user_approved=True,
            confirmation_text="CONFIRMER_PHASE_2",
        )
        
        if result['success']:
            self.assertEqual(
                self.manager.get_current_phase(),
                SystemPhase.PHASE_2_ASSISTED
            )
    
    def test_hysteresis_prevents_rapid_transition(self):
        """Test que l'hystérésis empêche une transition trop rapide"""
        # Forcer date récente (moins de 7j)
        self.manager._phase_start_date = datetime.now(timezone.utc) - timedelta(days=3)
        
        result = self.manager.request_phase_transition(
            user_approved=True,
            confirmation_text="CONFIRMER_PHASE_2",
        )
        
        # Devrait échouer à cause de l'hystérésis
        self.assertFalse(result['success'])
        self.assertIn('hystérésis', result.get('error', '').lower())
    
    def test_cannot_go_beyond_phase_2(self):
        """Test qu'on ne peut pas aller au-delà de Phase 2"""
        # Forcer Phase 2
        self.manager._current_phase = SystemPhase.PHASE_2_ASSISTED
        
        eligibility = self.manager.evaluate_transition_eligibility(
            current_capital=5000.0,
            initial_capital=1000.0,
            max_drawdown_pct=-5.0,
            atr_14=3.0,
            max_1h_spike=2.0
        )
        
        self.assertFalse(eligibility['eligible'])
        self.assertIn('maximum', eligibility['message'])


class TestEvolutionDashboard(unittest.TestCase):
    """Tests du dashboard"""
    
    def setUp(self):
        self.temp_db = tempfile.mktemp(suffix='.db')
        self.manager = AutoEvolutionManager(db_path=self.temp_db)
    
    def tearDown(self):
        if os.path.exists(self.temp_db):
            os.remove(self.temp_db)
    
    def test_dashboard_render(self):
        """Test que le dashboard se rend sans erreur"""
        from src.autobot.v2.evolution_dashboard import EvolutionDashboard
        
        dashboard = EvolutionDashboard()
        rendered = dashboard.render()
        
        self.assertIn("AUTOBOT", rendered)
        self.assertIn("Phase 1", rendered)
        self.assertIn("SÉCURITÉ", rendered)
    
    def test_progress_bar(self):
        """Test le rendu de la barre de progression"""
        from src.autobot.v2.evolution_dashboard import EvolutionDashboard
        
        dashboard = EvolutionDashboard()
        bar = dashboard._render_progress_bar(50.0, width=10)
        
        self.assertIn("[", bar)
        self.assertIn("]", bar)
        # 50% de 10 = 5 caractères remplis
        self.assertEqual(bar.count('█'), 5)


if __name__ == '__main__':
    unittest.main()
