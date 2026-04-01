"""
Dashboard d'évolution - Interface utilisateur pour AutoEvolutionManager
"""

import logging
from typing import Dict, Any
from .auto_evolution import get_auto_evolution_manager, SystemPhase

logger = logging.getLogger(__name__)


class EvolutionDashboard:
    """Dashboard texte pour l'évolution des phases"""
    
    def __init__(self):
        self.manager = get_auto_evolution_manager()
    
    def render(self, current_capital: float = 0, initial_capital: float = 0) -> str:
        """Rend le dashboard en texte"""
        data = self.manager.get_dashboard_data(current_capital, initial_capital)
        
        # Barre de progression
        progress_bar = self._render_progress_bar(data['progress_pct'])
        
        # Statut de transition
        if data['approval_pending']:
            transition_status = "⏳ EN ATTENTE D'APPROBATION"
        elif data.get('circuit_breaker_active'):
            transition_status = "🔒 CIRCUIT BREAKER (48h)"
        elif data['can_evolve'] and data['progress_pct'] >= 100:
            transition_status = "✅ PRÊT - Approuvez pour passer Phase 2"
        elif not data['can_evolve'] and data['current_phase'] == 'phase_2_assisted':
            transition_status = "🏁 PHASE MAXIMALE ATTEINTE"
        else:
            transition_status = "⏳ EN PROGRESSION"
        
        # Info croissance si disponible
        growth_info = ""
        if current_capital > 0 and initial_capital > 0:
            growth_info = f"║  📈 CROISSANCE : {data['growth_pct']:>+6.1f}% (min: {data['min_growth_required']:>+4.0f}%)      ║"
        
        dashboard = f"""
╔══════════════════════════════════════════════════════════════╗
║  🤖 AUTOBOT - Évolution Automatique (Sécurisé)              ║
╠══════════════════════════════════════════════════════════════╣
║                                                              ║
║  Phase Actuelle : {data['phase_name']:<36} ║
║  {data['phase_description']:<56} ║
║                                                              ║
║  Durée : {data['phase_duration_days']:>3}j / {data['min_duration_days']:>3}j minimum{' '*24} ║
║                                                              ║
║  Progression : {progress_bar:<44} ║
║                {data['progress_pct']:>5.1f}%{' '*43} ║
{growth_info:<56}
║                                                              ║
║  🛡️  LIMITES DE SÉCURITÉ :                                    ║
║     Drawdown max : {data['max_drawdown_limit']:>6.1f}%{' '*33} ║
║     Perte jour   : {data['daily_loss_limit']:>6.1f}%{' '*33} ║
║                                                              ║
║  📊 MARCHÉS ACTIFS :                                          ║
║     {', '.join(data['markets']):<54} ║
║                                                              ║
║  {transition_status:<56} ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝

Commandes disponibles :
  [1] Voir détails complets
  [2] Approuver transition Phase 2 (si prêt)
  [3] Retour Phase 1 (si tu regrettes Phase 2)
  [4] Voir historique
  [Q] Quitter

⚠️  IMPORTANT : Une fois Phase 2 approuvée, tu peux revenir en Phase 1
    mais cela fermera tes positions EUR/USD.
"""
        return dashboard
    
    def _render_progress_bar(self, pct: float, width: int = 30) -> str:
        """Rend une barre de progression ASCII"""
        filled = int(width * pct / 100)
        bar = '█' * filled + '░' * (width - filled)
        return f"[{bar}]"
    
    def check_and_notify(self, 
                         current_capital: float,
                         initial_capital: float,
                         max_drawdown_pct: float,
                         atr_14: float,
                         max_1h_spike: float) -> Dict[str, Any]:
        """
        Vérifie l'état et notifie si nécessaire.
        À appeler régulièrement (ex: toutes les heures).
        """
        # Vérifier hard stops en premier
        daily_loss = ((current_capital - initial_capital) / initial_capital) * 100
        hard_stop = self.manager.check_hard_stops(daily_loss, max_drawdown_pct)
        
        if hard_stop:
            return {
                'type': 'HARD_STOP',
                'data': hard_stop,
                'message': f"🚨 ALERTE CRITIQUE: {hard_stop['message']}"
            }
        
        # Vérifier transition
        if self.manager.get_current_phase() == SystemPhase.PHASE_1_SURVIVAL:
            eligibility = self.manager.evaluate_transition_eligibility(
                current_capital, initial_capital, max_drawdown_pct,
                atr_14, max_1h_spike
            )
            
            if eligibility['eligible'] and not eligibility.get('pending_approval'):
                return {
                    'type': 'TRANSITION_READY',
                    'data': eligibility,
                    'message': (
                        f"✅ TRANSITION PRÊTE!\n\n"
                        f"Critères atteints:\n"
                        f"  - Durée: OK\n"
                        f"  - Drawdown: {max_drawdown_pct:.1f}% (limite -15%)\n"
                        f"  - Capital: {current_capital:.0f}€ (min 1000€)\n"
                        f"  - ATR stable: {atr_14:.1f}%\n\n"
                        f"Approuvez pour activer Phase 2 (BTC/EUR + EUR/USD)"
                    )
                }
        
        return {
            'type': 'STATUS_OK',
            'data': self.manager.get_dashboard_data(),
            'message': 'Système nominal'
        }
    
    def approve_transition(self, confirmation: str = "") -> Dict[str, Any]:
        """Approuve la transition de phase (action utilisateur)"""
        # CORRECTION OPUS: Exiger confirmation textuelle
        result = self.manager.request_phase_transition(
            user_approved=True, 
            confirmation_text=confirmation
        )
        
        if result.get('requires_confirmation'):
            return {
                'success': False,
                'requires_confirmation': True,
                'message': (
                    "⚠️ CONFIRMATION REQUISE\n\n"
                    "Tu es sur le point d'activer la Phase 2.\n"
                    "Cette action est IRRÉVOCABLE (tu pourras revenir en Phase 1, "
                    "mais ce sera un reset).\n\n"
                    "Pour confirmer, tape exactement : CONFIRMER_PHASE_2"
                )
            }
        
        if result['success']:
            return {
                'success': True,
                'message': (
                    f"🚀 Transition approuvée!\n\n"
                    f"Nouvelle phase: {result['config']['name']}\n"
                    f"Marchés: {', '.join(result['config']['markets'])}\n"
                    f"Protection: Activée\n\n"
                    f"Le bot va maintenant trader sur plusieurs marchés "
                    f"avec protection automatique.\n\n"
                    f"Tu peux revenir en Phase 1 à tout moment si tu changes d'avis."
                )
            }
        elif result.get('pending_approval'):
            return {
                'success': False,
                'pending': True,
                'message': "Transition en attente. Vérifiez les critères d'abord."
            }
        else:
            return {
                'success': False,
                'error': result.get('error', 'Transition impossible')
            }
    
    def request_downgrade(self, reason: str = "") -> Dict[str, Any]:
        """Demande un retour à la Phase 1"""
        result = self.manager.request_downgrade_to_phase_1(
            user_confirmed=True,
            reason=reason
        )
        return result


# Helper pour notifications
class EvolutionNotifier:
    """Système de notifications pour l'évolution"""
    
    def __init__(self):
        self.manager = get_auto_evolution_manager()
        self._setup_callbacks()
    
    def _setup_callbacks(self):
        """Configure les callbacks de notification"""
        self.manager.set_callbacks(
            on_approval_request=self._on_approval_needed,
            on_phase_change=self._on_phase_changed,
            on_hard_stop=self._on_hard_stop_triggered
        )
    
    def _on_approval_needed(self, data: Dict[str, Any]):
        """Appelé quand une approbation est nécessaire"""
        logger.info(f"⏳ Approbation requise: {data}")
        # Ici: envoyer notification email/SMS/etc
    
    def _on_phase_changed(self, data: Dict[str, Any]):
        """Appelé quand la phase change"""
        logger.info(f"🚀 Phase changée: {data['old_phase']} → {data['new_phase']}")
        # Ici: logger, notifier, etc
    
    def _on_hard_stop_triggered(self, data: Dict[str, Any]):
        """Appelé quand un hard stop est déclenché"""
        logger.critical(f"🚨 HARD STOP: {data}")
        # Ici: arrêter tout trading, envoyer alerte urgente
