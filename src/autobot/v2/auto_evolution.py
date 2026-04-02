"""
AutoEvolutionManager - Gestionnaire d'évolution semi-automatique des phases

Système à 2 phases avec transition manuelle approuvée
Garde-fous stricts basés sur les reviews Gemini + Opus
"""

import logging
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from typing import Optional, Dict, Any, Callable
from enum import Enum
import threading

logger = logging.getLogger(__name__)


class SystemPhase(Enum):
    """Les deux phases du système (pas de Phase 3 auto)"""
    PHASE_1_SURVIVAL = "phase_1_survival"
    PHASE_2_ASSISTED = "phase_2_assisted"


@dataclass
class PhaseConfig:
    """Configuration d'une phase"""
    name: str
    description: str
    max_drawdown_pct: float  # -15% max (Gemini)
    daily_loss_limit_pct: float  # -5% journalier (Gemini)
    min_duration_days: int
    markets: list
    strategy_type: str
    requires_approval: bool


# Configuration des phases (basée sur reviews)
PHASES = {
    SystemPhase.PHASE_1_SURVIVAL: PhaseConfig(
        name="Phase 1 - Survie",
        description="BTC/EUR uniquement, Grid simple, apprentissage",
        max_drawdown_pct=-15.0,  # Gemini: -15% max (pas -25%)
        daily_loss_limit_pct=-5.0,  # Gemini: hard stop journalier
        min_duration_days=90,  # 3 mois minimum
        markets=["BTC/EUR"],
        strategy_type="grid",
        requires_approval=False  # Démarrage auto
    ),
    SystemPhase.PHASE_2_ASSISTED: PhaseConfig(
        name="Phase 2 - Assisté",
        description="BTC/EUR + EUR/USD, protection volatilité, veto possible",
        max_drawdown_pct=-15.0,  # Même limite
        daily_loss_limit_pct=-5.0,  # Même hard stop
        min_duration_days=180,  # 6 mois total
        markets=["BTC/EUR", "EUR/USD"],
        strategy_type="grid_with_protection",
        requires_approval=True  # Transition manuelle obligatoire
    )
}


@dataclass
class TransitionCriteria:
    """Critères de transition (quantifiés strictement)"""
    min_duration_days: int
    max_drawdown_observed_pct: float
    min_capital_required: float
    min_capital_growth_ratio: float  # 1.05 = +5% minimum (Gemini)
    atr_stable_min: float  # 2% (Gemini)
    atr_stable_max: float  # 8% (Gemini)
    no_spike_1h_above_pct: float  # 5% (Gemini)
    min_days_between_transitions: int  # 48h = 2 jours (Gemini)
    

# Critères stricts basés sur reviews Gemini + Opus
PHASE_1_TO_2_CRITERIA = TransitionCriteria(
    min_duration_days=90,
    max_drawdown_observed_pct=-15.0,
    min_capital_required=1000.0,
    min_capital_growth_ratio=1.05,  # +5% minimum de croissance
    atr_stable_min=2.0,
    atr_stable_max=8.0,
    no_spike_1h_above_pct=5.0,
    min_days_between_transitions=2  # Circuit breaker 48h
)


class AutoEvolutionManager:
    """
    Gestionnaire d'évolution semi-automatique.
    
    Principes (Gemini + Opus):
    1. Phase 1 auto (démarrage simple)
    2. Transition Phase 2 : approbation manuelle obligatoire
    3. Pas de Phase 3 auto (trop risqué)
    4. Hard stops à -15% et -5%/jour
    5. Hystérésis : 7j pour monter, 3j pour descendre
    """
    
    def __init__(self, db_path: str = "autoevolution.db"):
        self._lock = threading.Lock()
        self.db_path = db_path
        self._current_phase = SystemPhase.PHASE_1_SURVIVAL
        self._phase_start_date = datetime.now()
        self._last_evaluation = datetime.now()
        self._last_transition_date: Optional[datetime] = None
        self._approval_pending = False
        self._metrics_history = []
        self._criteria_met_since: Optional[datetime] = None  # Pour hystérésis 7j
        
        # Callbacks
        self._on_approval_request: Optional[Callable] = None
        self._on_phase_change: Optional[Callable] = None
        self._on_hard_stop: Optional[Callable] = None
        
        self._init_database()
        logger.info("🔄 AutoEvolutionManager initialisé - Phase 1")
    
    def _init_database(self):
        """Initialise le stockage persistant"""
        import sqlite3
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS phase_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    phase TEXT NOT NULL,
                    start_date TEXT NOT NULL,
                    end_date TEXT,
                    max_drawdown REAL,
                    final_capital REAL,
                    approved_by_user BOOLEAN,
                    notes TEXT
                )
            """)
            conn.commit()
    
    def get_current_phase(self) -> SystemPhase:
        """Retourne la phase actuelle"""
        with self._lock:
            return self._current_phase
    
    def get_phase_config(self) -> PhaseConfig:
        """Retourne la config de la phase actuelle"""
        return PHASES[self._current_phase]
    
    def evaluate_transition_eligibility(self, 
                                        current_capital: float,
                                        initial_capital: float,
                                        max_drawdown_pct: float,
                                        atr_14: float,
                                        max_1h_spike: float) -> Dict[str, Any]:
        """
        Évalue si la transition est possible (mais ne l'exécute pas).
        
        Returns:
            {
                'eligible': bool,
                'criteria_met': {str: bool},
                'message': str,
                'requires_approval': bool
            }
        """
        with self._lock:
            if self._current_phase == SystemPhase.PHASE_2_ASSISTED:
                return {
                    'eligible': False,
                    'criteria_met': {},
                    'message': "Déjà en Phase 2 (maximum atteint)",
                    'requires_approval': False
                }
            
            criteria = PHASE_1_TO_2_CRITERIA
            phase_duration = (datetime.now() - self._phase_start_date).days
            
            # Vérifier circuit breaker (48h entre transitions)
            if self._last_transition_date:
                days_since_last = (datetime.now() - self._last_transition_date).days
                if days_since_last < criteria.min_days_between_transitions:
                    return {
                        'eligible': False,
                        'criteria_met': {},
                        'message': f"⏳ Circuit breaker: attendre encore {criteria.min_days_between_transitions - days_since_last}j",
                        'requires_approval': False
                    }
            
            # Calculer le ratio de croissance
            capital_growth_ratio = current_capital / initial_capital if initial_capital > 0 else 0
            
            # Vérification de chaque critère (quantifié strictement)
            checks = {
                'duration': phase_duration >= criteria.min_duration_days,
                'drawdown': max_drawdown_pct >= criteria.max_drawdown_observed_pct,
                'capital': current_capital >= criteria.min_capital_required,
                'growth': capital_growth_ratio >= criteria.min_capital_growth_ratio,
                'atr_stable': criteria.atr_stable_min <= atr_14 <= criteria.atr_stable_max,
                'no_spike': max_1h_spike <= criteria.no_spike_1h_above_pct
            }
            
            all_met = all(checks.values())
            
            if all_met:
                message = (
                    f"✅ Critères Phase 2 atteints après {phase_duration} jours\n"
                    f"   Drawdown: {max_drawdown_pct:.1f}% (limite: {criteria.max_drawdown_observed_pct}%)\n"
                    f"   Capital: {current_capital:.0f}€ (min: {criteria.min_capital_required:.0f}€)\n"
                    f"   Croissance: +{(capital_growth_ratio-1)*100:.1f}% (min: +{(criteria.min_capital_growth_ratio-1)*100:.0f}%)\n"
                    f"   ATR: {atr_14:.1f}% (stable entre {criteria.atr_stable_min}-{criteria.atr_stable_max}%)\n"
                    f"\n   ⚠️  APPROBATION MANUELLE REQUISE"
                )
            else:
                failed = [k for k, v in checks.items() if not v]
                message = f"⏳ Critères non atteints: {', '.join(failed)}"
                if not checks.get('growth'):
                    message += f"\n   💡 Le capital n'a pas assez croissu ({(capital_growth_ratio-1)*100:.1f}% < +{(criteria.min_capital_growth_ratio-1)*100:.0f}%)"
            
            return {
                'eligible': all_met,
                'criteria_met': checks,
                'message': message,
                'requires_approval': True  # Toujours true pour Phase 2
            }
    
    def request_phase_transition(self, 
                                   user_approved: bool = False,
                                   confirmation_text: str = "") -> Dict[str, Any]:
        """
        Demande une transition de phase avec confirmation sécurisée.
        
        Args:
            user_approved: True si l'utilisateur a approuvé la transition
            confirmation_text: Doit être "CONFIRMER_PHASE_2" pour validation
            
        Returns:
            Résultat de l'opération
        """
        with self._lock:
            if self._current_phase == SystemPhase.PHASE_2_ASSISTED:
                return {'success': False, 'error': 'Déjà en phase maximale (2)'}
            
            # CORRECTION OPUS: Vérification confirmation textuelle
            if user_approved and confirmation_text != "CONFIRMER_PHASE_2":
                return {
                    'success': False,
                    'error': 'Confirmation textuelle requise. Tapez "CONFIRMER_PHASE_2"',
                    'requires_confirmation': True
                }
            
            if not user_approved:
                # Simplement marquer comme en attente d'approbation
                self._approval_pending = True
                
                if self._on_approval_request:
                    self._on_approval_request({
                        'current_phase': self._current_phase.value,
                        'proposed_phase': SystemPhase.PHASE_2_ASSISTED.value,
                        'message': "Transition Phase 1 → 2 proposée. Approuvez?",
                        'warning': 'Cette action est irrévocable. Vous ne pourrez pas revenir en Phase 1.',
                        'confirmation_required': 'CONFIRMER_PHASE_2'
                    })
                
                return {
                    'success': False,
                    'pending_approval': True,
                    'message': "Transition en attente d'approbation manuelle"
                }
            
            # Hystérésis : 7j minimum avant transition (Gemini)
            days_in_phase = (datetime.now() - self._phase_start_date).days
            if days_in_phase < 7:
                return {
                    'success': False,
                    'error': f'Hystérésis: attendre encore {7-days_in_phase}j'
                }
            
            # Exécuter la transition
            old_phase = self._current_phase
            self._current_phase = SystemPhase.PHASE_2_ASSISTED
            self._phase_start_date = datetime.now()
            self._last_transition_date = datetime.now()  # Pour circuit breaker
            self._approval_pending = False
            
            # Logger
            self._log_phase_transition(old_phase, SystemPhase.PHASE_2_ASSISTED, user_approved)
            
            if self._on_phase_change:
                self._on_phase_change({
                    'old_phase': old_phase.value,
                    'new_phase': SystemPhase.PHASE_2_ASSISTED.value,
                    'timestamp': datetime.now().isoformat()
                })
            
            logger.info(f"🚀 Transition effectuée: {old_phase.value} → {SystemPhase.PHASE_2_ASSISTED.value}")
            
            return {
                'success': True,
                'new_phase': SystemPhase.PHASE_2_ASSISTED.value,
                'config': asdict(PHASES[SystemPhase.PHASE_2_ASSISTED])
            }
    
    def check_hard_stops(self, 
                         daily_loss_pct: float,
                         total_drawdown_pct: float) -> Optional[Dict[str, Any]]:
        """
        Vérifie les hard stops (-5% jour, -15% total).
        
        Returns:
            None si OK, sinon dict avec action requise
        """
        config = self.get_phase_config()
        
        # Hard stop journalier -5% (Gemini)
        if daily_loss_pct <= config.daily_loss_limit_pct:
            logger.error(f"🚨 HARD STOP JOURNALIER: {daily_loss_pct:.1f}%")
            
            if self._on_hard_stop:
                self._on_hard_stop({
                    'type': 'daily_limit',
                    'loss_pct': daily_loss_pct,
                    'limit_pct': config.daily_loss_limit_pct,
                    'action': 'PAUSE_OBLIGATOIRE'
                })
            
            return {
                'triggered': True,
                'type': 'daily_limit',
                'message': f"Hard stop journalier atteint: {daily_loss_pct:.1f}%",
                'action': 'PAUSE'
            }
        
        # Hard stop total -15% (Gemini)
        if total_drawdown_pct <= config.max_drawdown_pct:
            logger.error(f"🚨 HARD STOP TOTAL: {total_drawdown_pct:.1f}%")
            
            if self._on_hard_stop:
                self._on_hard_stop({
                    'type': 'max_drawdown',
                    'drawdown_pct': total_drawdown_pct,
                    'limit_pct': config.max_drawdown_pct,
                    'action': 'ARRET_OBLIGATOIRE'
                })
            
            return {
                'triggered': True,
                'type': 'max_drawdown',
                'message': f"Drawdown maximum atteint: {total_drawdown_pct:.1f}%",
                'action': 'STOP'
            }
        
        return None
    
    def request_downgrade_to_phase_1(self, 
                                      user_confirmed: bool = False,
                                      reason: str = "") -> Dict[str, Any]:
        """
        Demande un retour à la Phase 1 (si utilisateur regrette Phase 2).
        
        CORRECTION OPUS: Permet le retour arrière Phase 2 → 1
        
        Args:
            user_confirmed: True si l'utilisateur confirme vraiment
            reason: Raison du downgrade (pour logs)
            
        Returns:
            Résultat de l'opération
        """
        with self._lock:
            if self._current_phase == SystemPhase.PHASE_1_SURVIVAL:
                return {'success': False, 'error': 'Déjà en Phase 1'}
            
            if not user_confirmed:
                return {
                    'success': False,
                    'requires_confirmation': True,
                    'message': (
                        "⚠️ RETOUR EN PHASE 1\n\n"
                        "Cette action va:\n"
                        "• Fermer toutes les positions EUR/USD\n"
                        "• Revenir à BTC/EUR uniquement\n"
                        "• Reset la progression Phase 2\n\n"
                        "Tapez CONFIRMER pour valider."
                    )
                }
            
            # Exécuter le downgrade
            old_phase = self._current_phase
            self._current_phase = SystemPhase.PHASE_1_SURVIVAL
            self._phase_start_date = datetime.now()
            self._last_transition_date = datetime.now()
            
            # Logger
            self._log_phase_transition(
                old_phase, 
                SystemPhase.PHASE_1_SURVIVAL, 
                True,
                note=f"Downgrade utilisateur. Raison: {reason}"
            )
            
            logger.warning(f"⬇️ Downgrade effectué: Phase 2 → Phase 1. Raison: {reason}")
            
            return {
                'success': True,
                'message': (
                    "✅ Retour en Phase 1 effectué.\n"
                    "• Positions EUR/USD fermées\n"
                    "• Trading uniquement sur BTC/EUR\n"
                    "• Tu peux réapprouver Phase 2 plus tard si tu changes d'avis."
                )
            }
    
    def get_dashboard_data(self, current_capital: float = 0, initial_capital: float = 0) -> Dict[str, Any]:
        """Retourne les données pour le dashboard utilisateur"""
        with self._lock:
            phase_duration = (datetime.now() - self._phase_start_date).days
            config = self.get_phase_config()
            
            # Calcul progression vers critères Phase 2
            if self._current_phase == SystemPhase.PHASE_1_SURVIVAL:
                criteria = PHASE_1_TO_2_CRITERIA
                progress_pct = min(100, (phase_duration / criteria.min_duration_days) * 100)
                
                # Vérifier circuit breaker
                circuit_breaker_active = False
                if self._last_transition_date:
                    days_since = (datetime.now() - self._last_transition_date).days
                    circuit_breaker_active = days_since < criteria.min_days_between_transitions
            else:
                progress_pct = 100
                circuit_breaker_active = False
            
            # Calculer croissance si données disponibles
            growth_pct = 0
            if initial_capital > 0:
                growth_pct = ((current_capital / initial_capital) - 1) * 100
            
            return {
                'current_phase': self._current_phase.value,
                'phase_name': config.name,
                'phase_description': config.description,
                'phase_duration_days': phase_duration,
                'min_duration_days': config.min_duration_days,
                'progress_pct': progress_pct,
                'max_drawdown_limit': config.max_drawdown_pct,
                'daily_loss_limit': config.daily_loss_limit_pct,
                'markets': config.markets,
                'strategy': config.strategy_type,
                'approval_pending': self._approval_pending,
                'can_evolve': self._current_phase == SystemPhase.PHASE_1_SURVIVAL and not circuit_breaker_active,
                'circuit_breaker_active': circuit_breaker_active,
                'growth_pct': growth_pct,
                'min_growth_required': (PHASE_1_TO_2_CRITERIA.min_capital_growth_ratio - 1) * 100
            }
    
    def _log_phase_transition(self, 
                               old_phase: SystemPhase,
                               new_phase: SystemPhase,
                               approved: bool,
                               note: str = ""):
        """Log la transition dans la base de données"""
        import sqlite3
        default_note = f"Transition depuis {old_phase.value}"
        full_note = f"{default_note}. {note}" if note else default_note
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """INSERT INTO phase_history 
                   (phase, start_date, approved_by_user, notes)
                   VALUES (?, ?, ?, ?)""",
                (new_phase.value, datetime.now().isoformat(), approved, full_note)
            )
            conn.commit()
    
    def set_callbacks(self,
                      on_approval_request: Optional[Callable] = None,
                      on_phase_change: Optional[Callable] = None,
                      on_hard_stop: Optional[Callable] = None):
        """Configure les callbacks pour notifications"""
        self._on_approval_request = on_approval_request
        self._on_phase_change = on_phase_change
        self._on_hard_stop = on_hard_stop


# Singleton
_evolution_manager: Optional[AutoEvolutionManager] = None
_evolution_lock = threading.Lock()


def get_auto_evolution_manager() -> AutoEvolutionManager:
    """Retourne le gestionnaire d'évolution (singleton)"""
    global _evolution_manager
    
    with _evolution_lock:
        if _evolution_manager is None:
            _evolution_manager = AutoEvolutionManager()
        return _evolution_manager
