"""
Validator Engine - Vérification "voyants au vert" avant chaque action
"""

import logging
from typing import Dict, List, Callable, Optional, Any
from dataclasses import dataclass
from enum import Enum
from datetime import datetime, timedelta
from collections import deque

logger = logging.getLogger(__name__)


class ValidationStatus(Enum):
    """Statut de validation"""
    GREEN = "green"      # ✅ Tout OK
    YELLOW = "yellow"    # ⚠️ Attention mais faisable
    RED = "red"          # ❌ Bloquant


@dataclass
class ValidationResult:
    """Résultat d'une validation"""
    status: ValidationStatus
    action: str
    message: str
    details: Dict[str, Any]
    timestamp: datetime


class ValidatorEngine:
    """
    Moteur de validation "voyants au vert".
    
    Avant chaque action importante (spin-off, levier, trade), 
    vérifie que toutes les conditions sont réunies.
    """
    
    def __init__(self):
        self._validators: Dict[str, List[Callable]] = {
            'spin_off': [],
            'leverage': [],
            'modify_tp_sl': [],
            'open_position': [],
            'close_position': []
        }
        # CORRECTION: Utiliser deque pour performance O(1) et thread safety
        self._max_history = 1000
        self._history: deque = deque(maxlen=self._max_history)
        
        # Seuils par défaut
        self.thresholds = {
            'spin_off_capital': 2000.0,
            'leverage_capital': 1000.0,
            'spin_off_min_profit': 100.0,
            'max_drawdown': 0.20,  # 20%
            'min_win_streak': 5,
            'max_volatility': 0.10,  # 10%
            'max_instances': 5
        }
        
        logger.info("✅ ValidatorEngine initialisé")
    
    def register_validator(self, action: str, validator: Callable):
        """Enregistre un validateur pour une action"""
        if action not in self._validators:
            raise ValueError(f"Action inconnue: {action}")
        
        self._validators[action].append(validator)
        logger.debug(f"📝 Validateur ajouté pour {action}")
    
    def validate(self, action: str, context: Dict[str, Any]) -> ValidationResult:
        """
        Valide une action avec tous les validateurs enregistrés.
        
        Args:
            action: Type d'action ('spin_off', 'leverage', etc.)
            context: Données contextuelles (capital, performance, marché...)
            
        Returns:
            ValidationResult avec statut et détails
        """
        if action not in self._validators:
            result = ValidationResult(
                status=ValidationStatus.RED,
                action=action,
                message=f"Action inconnue: {action}",
                details={},
                timestamp=datetime.now()
            )
            self._log_result(result)
            return result
        
        # Exécute tous les validateurs
        all_checks = []
        messages = []
        
        for validator in self._validators[action]:
            try:
                check_result = validator(context)
                all_checks.append(check_result)
                
                if not check_result.get('passed', False):
                    messages.append(check_result.get('message', 'Échec validation'))
                    
            except Exception as e:
                logger.error(f"❌ Erreur validateur: {e}")
                all_checks.append({'passed': False, 'message': str(e)})
                messages.append(str(e))
        
        # Détermine statut global
        if any(not c.get('passed', False) for c in all_checks):
            status = ValidationStatus.RED
            message = "; ".join(messages) if messages else "Validation échouée"
        elif any(c.get('warning', False) for c in all_checks):
            status = ValidationStatus.YELLOW
            message = "Validation OK avec avertissements"
        else:
            status = ValidationStatus.GREEN
            message = "Tous les voyants sont au vert"
        
        result = ValidationResult(
            status=status,
            action=action,
            message=message,
            details={
                'checks': all_checks,
                'context': context
            },
            timestamp=datetime.now()
        )
        
        self._log_result(result)
        return result
    
    def _log_result(self, result: ValidationResult):
        """Log le résultat"""
        emoji = "🟢" if result.status == ValidationStatus.GREEN else "🟡" if result.status == ValidationStatus.YELLOW else "🔴"
        logger.info(f"{emoji} Validation {result.action}: {result.message}")
        
        self._history.append(result)
        # CORRECTION: deque gère auto la taille max, plus besoin de slicing
    
    def get_history(self, action: Optional[str] = None, 
                    since: Optional[datetime] = None) -> List[ValidationResult]:
        """Retourne l'historique des validations"""
        results = self._history
        
        if action:
            results = [r for r in results if r.action == action]
        
        if since:
            results = [r for r in results if r.timestamp >= since]
        
        # CORRECTION: Retourner une liste (pas deque) pour compatibilité JSON
        return list(results)
    
    def can_execute(self, action: str, context: Dict[str, Any]) -> bool:
        """Vérifie si action peut être exécutée (statut GREEN ou YELLOW)"""
        result = self.validate(action, context)
        return result.status in (ValidationStatus.GREEN, ValidationStatus.YELLOW)


# Validateurs prédéfinis

class DefaultValidators:
    """Validateurs par défaut pour AUTOBOT V2"""
    
    @staticmethod
    def spin_off_validator(context: Dict) -> Dict:
        """Valide conditions spin-off"""
        capital = context.get('capital', 0)
        threshold = context.get('threshold', 2000)
        available_capital = context.get('available_capital', 0)
        min_capital = context.get('min_capital', 500)
        instance_count = context.get('instance_count', 0)
        max_instances = context.get('max_instances', 5)
        volatility = context.get('volatility', 0)
        max_volatility = context.get('max_volatility', 0.10)
        
        checks = []
        
        # Check 1: Seuil atteint
        if capital >= threshold:
            checks.append({'name': 'seuil', 'passed': True, 'value': capital})
        else:
            return {
                'passed': False,
                'message': f'Capital {capital:.2f}€ < seuil {threshold:.2f}€'
            }
        
        # Check 2: Capital disponible
        if available_capital >= min_capital:
            checks.append({'name': 'capital_dispo', 'passed': True, 'value': available_capital})
        else:
            return {
                'passed': False,
                'message': f'Capital disponible insuffisant: {available_capital:.2f}€'
            }
        
        # Check 3: Max instances
        if instance_count < max_instances:
            checks.append({'name': 'max_instances', 'passed': True, 'value': instance_count})
        else:
            return {
                'passed': False,
                'message': f'Limite instances atteinte: {instance_count}/{max_instances}'
            }
        
        # Check 4: Volatilité
        if volatility <= max_volatility:
            checks.append({'name': 'volatilite', 'passed': True, 'value': volatility})
        else:
            return {
                'passed': False,
                'message': f'Volatilité trop élevée: {volatility:.2%} > {max_volatility:.2%}'
            }
        
        return {'passed': True, 'checks': checks}
    
    @staticmethod
    def leverage_validator(context: Dict) -> Dict:
        """Valide conditions activation levier"""
        capital = context.get('capital', 0)
        threshold = context.get('threshold', 1000)
        win_streak = context.get('win_streak', 0)
        min_win_streak = context.get('min_win_streak', 5)
        drawdown = context.get('drawdown', 0)
        max_drawdown = context.get('max_drawdown', 0.10)
        trend = context.get('trend', 'unknown')
        
        # Check 1: Seuil capital
        if capital < threshold:
            return {
                'passed': False,
                'message': f'Capital {capital:.2f}€ < seuil levier {threshold:.2f}€'
            }
        
        # Check 2: Win streak
        if win_streak < min_win_streak:
            return {
                'passed': False,
                'message': f'Win streak {win_streak} < minimum {min_win_streak}'
            }
        
        # Check 3: Drawdown
        if drawdown > max_drawdown:
            return {
                'passed': False,
                'message': f'Drawdown {drawdown:.2%} > maximum {max_drawdown:.2%}'
            }
        
        # Check 4: Trend clair (warning si pas clair)
        if trend not in ('up', 'down'):
            return {
                'passed': True,
                'warning': True,
                'message': f'Marché en range, levier risqué'
            }
        
        return {'passed': True, 'trend': trend}
    
    @staticmethod
    def open_position_validator(context: Dict) -> Dict:
        """Valide conditions ouverture position"""
        balance = context.get('balance', 0)
        order_value = context.get('order_value', 0)
        open_positions = context.get('open_positions', 0)
        max_positions = context.get('max_positions', 10)
        price = context.get('price', 0)
        range_min = context.get('range_min', 0)
        range_max = context.get('range_max', float('inf'))
        
        # Check 1: Solde suffisant
        if balance < order_value:
            return {
                'passed': False,
                'message': f'Solde insuffisant: {balance:.2f}€ < {order_value:.2f}€'
            }
        
        # Check 2: Max positions
        if open_positions >= max_positions:
            return {
                'passed': False,
                'message': f'Max positions atteint: {open_positions}/{max_positions}'
            }
        
        # Check 3: Prix dans range acceptable
        if price < range_min or price > range_max:
            return {
                'passed': False,
                'message': f'Prix {price:.2f} hors range [{range_min:.2f}, {range_max:.2f}]'
            }
        
        return {'passed': True}


# Setup par défaut
def create_default_validator_engine() -> ValidatorEngine:
    """Crée un ValidatorEngine avec les validateurs par défaut"""
    engine = ValidatorEngine()
    
    defaults = DefaultValidators()
    
    engine.register_validator('spin_off', defaults.spin_off_validator)
    engine.register_validator('leverage', defaults.leverage_validator)
    engine.register_validator('open_position', defaults.open_position_validator)
    
    logger.info("✅ ValidatorEngine configuré avec validateurs par défaut")
    return engine
