# PROMPT DEVIN - ASSEMBLAGE AUTOBOT
## Budget: 2-3 ACUs maximum

**CONTEXTE:**
Tu dois assembler les scripts existants en un bot fonctionnel. Ne recrée PAS ce qui existe déjà. Corrige les imports cassés et crée l'orchestrateur.

**FICHIERS EXISTANTS (fonctionnels, ne pas modifier):**
- `scripts/kraken_connect.py` - Connexion API Kraken via ccxt
- `scripts/get_price.py` - Récupération prix BTC/EUR
- `scripts/grid_calculator.py` - Calcul 15 niveaux grid
- `src/autobot/error_handler.py` - Gestion erreurs complète

**FICHIERS À CORRIGER (imports cassés):**
- `scripts/order_manager.py` - Ligne 38-42: import depuis `src/grid_engine/` qui n'existe pas dans le contexte scripts/
- `scripts/position_manager.py` - Même problème d'import

**À CRÉER:**
- `scripts/main.py` - Orchestrateur principal qui enchaîne tout

---

## TÂCHE 1: Corriger les imports (15 min)

**Dans `scripts/order_manager.py`:**
```python
# SUPPRIMER ces lignes (38-42):
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
GRID_ENGINE_DIR = os.path.join(SCRIPT_DIR, '..', 'src', 'grid_engine')
sys.path.insert(0, GRID_ENGINE_DIR)
from grid_calculator import GridCalculator, GridConfig, GridLevel

# REMPLACER par:
from grid_calculator import GridConfig, GridLevel, calculate_grid_levels
```

**Adapter le code** pour utiliser `calculate_grid_levels()` au lieu de `GridCalculator`

**Dans `scripts/position_manager.py`:**
- Même correction d'import
- Adapter pour utiliser les fonctions de `grid_calculator.py`

---

## TÂCHE 2: Créer `scripts/main.py` (45 min)

**Structure du fichier:**
```python
#!/usr/bin/env python3
"""
AUTOBOT - Bot de Trading Grid
Orchestrateur principal qui enchaîne tous les modules.
"""

import os
import sys
import time
import json
import logging
from datetime import datetime
from typing import List, Dict, Optional

# Imports des scripts existants
from kraken_connect import create_kraken_client
from get_price import get_current_price
from grid_calculator import GridConfig, calculate_grid_levels, display_grid
from order_manager import place_buy_order, check_eur_balance
from position_manager import monitor_and_place_sells
from error_handler import retry_with_backoff, CircuitBreaker

# Configuration
GRID_CAPITAL = 500.0
GRID_LEVELS = 15
GRID_RANGE = 14.0  # +/- 7%
POLL_INTERVAL = 10  # secondes
STATE_FILE = "bot_state.json"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)


class GridTradingBot:
    """Bot de trading grid principal."""
    
    def __init__(self):
        self.exchange = None
        self.config = GridConfig(
            symbol="BTC/EUR",
            kraken_symbol="XXBTZEUR",
            capital_total=GRID_CAPITAL,
            num_levels=GRID_LEVELS,
            range_percent=GRID_RANGE
        )
        self.state = self.load_state()
        self.circuit_breaker = CircuitBreaker()
        
    def load_state(self) -> Dict:
        """Charge l'état depuis le fichier JSON."""
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, 'r') as f:
                return json.load(f)
        return {"orders": [], "positions": [], "initialized": False}
    
    def save_state(self):
        """Sauvegarde l'état dans le fichier JSON."""
        with open(STATE_FILE, 'w') as f:
            json.dump(self.state, f, indent=2)
    
    @retry_with_backoff(max_retries=3)
    def connect(self):
        """Connexion à Kraken."""
        self.exchange = create_kraken_client()
        logger.info("✅ Connecté à Kraken")
    
    def initialize_grid(self):
        """Initialise le grid au démarrage."""
        if self.state.get("initialized"):
            logger.info("Grid déjà initialisé, reprise...")
            return
            
        # Récupère prix actuel
        price_data = get_current_price(self.config.kraken_symbol)
        current_price = price_data["price"]
        logger.info(f"Prix BTC/EUR: {current_price:.2f}")
        
        # Calcule les niveaux
        levels = calculate_grid_levels(current_price, self.config)
        display_grid(levels, current_price, self.config)
        
        # Place les ordres d'achat initiaux (levels 0-6)
        buy_levels = [l for l in levels if l.level_type == "BUY"]
        logger.info(f"Placement de {len(buy_levels)} ordres d'achat...")
        
        for level in buy_levels:
            try:
                order = place_buy_order(
                    exchange=self.exchange,
                    price=level.price,
                    volume_btc=level.btc_quantity,
                    level_id=level.level
                )
                self.state["orders"].append(order.to_dict())
                logger.info(f"✅ Ordre BUY Level {level.level} placé: {order.exchange_order_id}")
            except Exception as e:
                logger.error(f"❌ Erreur placement Level {level.level}: {e}")
        
        self.state["initialized"] = True
        self.save_state()
        logger.info("✅ Grid initialisé")
    
    def run(self):
        """Boucle principale du bot."""
        logger.info("🚀 Démarrage AUTOBOT Grid Trading")
        
        try:
            self.connect()
            self.initialize_grid()
            
            logger.info(f"⏱️ Boucle principale (intervalle: {POLL_INTERVAL}s)")
            
            while True:
                try:
                    if self.circuit_breaker.is_open():
                        logger.warning("🚨 Circuit breaker ouvert, pause...")
                        time.sleep(60)
                        continue
                    
                    # Surveille les fills et place les ventes
                    new_positions = monitor_and_place_sells(
                        exchange=self.exchange,
                        open_orders=self.state["orders"],
                        state=self.state
                    )
                    
                    if new_positions:
                        self.state["positions"].extend(new_positions)
                        self.save_state()
                    
                    time.sleep(POLL_INTERVAL)
                    
                except Exception as e:
                    logger.error(f"❌ Erreur dans la boucle: {e}")
                    self.circuit_breaker.record_failure()
                    time.sleep(POLL_INTERVAL)
                    
        except KeyboardInterrupt:
            logger.info("🛑 Arrêt demandé par l'utilisateur")
            self.save_state()
        except Exception as e:
            logger.error(f"🚨 Erreur fatale: {e}")
            self.save_state()
            raise


if __name__ == "__main__":
    bot = GridTradingBot()
    bot.run()
```

---

## TÂCHE 3: Créer `scripts/persistence.py` (15 min)

**Gestion d'état JSON simple:**
```python
"""Module de persistance pour sauvegarder l'état du bot."""
import json
import os
from datetime import datetime
from typing import Dict, Any, List

STATE_FILE = "bot_state.json"

def save_state(orders: List[Dict], positions: List[Dict], metrics: Dict) -> None:
    """Sauvegarde l'état dans un fichier JSON."""
    state = {
        "last_update": datetime.now().isoformat(),
        "orders": orders,
        "positions": positions,
        "metrics": metrics
    }
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)

def load_state() -> Dict[str, Any]:
    """Charge l'état depuis le fichier JSON."""
    if not os.path.exists(STATE_FILE):
        return {"orders": [], "positions": [], "metrics": {}}
    with open(STATE_FILE, 'r') as f:
        return json.load(f)
```

---

## TÂCHE 4: Tester localement (15 min)

**Créer `scripts/test_assembly.py`:**
```python
"""Test rapide de l'assemblage (sans appeler Kraken)."""
import sys

def test_imports():
    """Vérifie que tous les imports fonctionnent."""
    try:
        from kraken_connect import create_kraken_client
        from get_price import get_current_price
        from grid_calculator import GridConfig, calculate_grid_levels
        from order_manager import place_buy_order
        from position_manager import monitor_and_place_sells
        from error_handler import retry_with_backoff
        print("✅ Tous les imports fonctionnent")
        return True
    except Exception as e:
        print(f"❌ Erreur d'import: {e}")
        return False

def test_grid_calculation():
    """Test le calcul de grid."""
    try:
        from grid_calculator import GridConfig, calculate_grid_levels
        config = GridConfig(
            symbol="BTC/EUR",
            kraken_symbol="XXBTZEUR",
            capital_total=500.0,
            num_levels=15,
            range_percent=14.0
        )
        levels = calculate_grid_levels(55000.0, config)
        assert len(levels) == 15
        assert levels[0].level_type == "BUY"
        assert levels[7].level_type == "CENTER"
        assert levels[14].level_type == "SELL"
        print("✅ Calcul de grid OK")
        return True
    except Exception as e:
        print(f"❌ Erreur grid: {e}")
        return False

if __name__ == "__main__":
    print("🧪 Test d'assemblage AUTOBOT")
    print("=" * 40)
    
    success = True
    success &= test_imports()
    success &= test_grid_calculation()
    
    print("=" * 40)
    if success:
        print("✅ Tous les tests passent")
        sys.exit(0)
    else:
        print("❌ Des erreurs ont été détectées")
        sys.exit(1)
```

---

## CRITÈRES DE SUCCÈS:

1. ✅ `python scripts/test_assembly.py` passe sans erreur
2. ✅ `python scripts/main.py --dry-run` démarre sans erreur d'import
3. ✅ Les ordres BUY sont placés sur Kraken (test avec petit capital)
4. ✅ Le fichier `bot_state.json` est créé et mis à jour
5. ✅ Les logs montrent le cycle complet

## CONTRAINTES:

- NE PAS modifier la logique des scripts existants (sauf imports)
- NE PAS créer de nouvelles classes inutiles
- PAS de tests unitaires complexes (on teste en live)
- MAXIMUM 2-3 ACUs

## FORMAT LIVRABLE:

1. PR #51: Correction des imports
2. PR #52: Création main.py + persistence.py + test_assembly.py
3. Documentation: `docs/BOT_ASSEMBLY.md` avec instructions de lancement

---

Lance cette tâche maintenant. Sois rigoureux sur les imports et teste avant de push.
