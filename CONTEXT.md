# AutoBot — Contexte Projet

## État actuel
- **Phase active** : Fin de développement core, prêt pour modules de performance
- **Modules implémentés** : Grid Strategy, Trend Strategy, Orchestrator, OrderExecutor, StopLossManager, ReconciliationManager, RiskManager, AutoEvolutionManager, Dashboard API
- **Modules dormants** : Mean Reversion, Arbitrage Triangulaire, Trend Following (partiel)
- **Dernière session** : 2026-04-01 — Audit complet et mise en place workflow multi-agents

## Architecture système
- **Langage** : Python 3.11+
- **Connecteur** : Kraken API (REST + WebSocket persistant)
- **Pattern** : Multi-instances Grid Trading avec auto-scaling
- **Capacité max** : 50 instances (actuellement limité à 5)
- **Dashboard** : FastAPI + React (lecture seule)

## Décisions architecturales

### [2026-03-11] WebSocket Kraken obligatoire, pas de REST répétitif
- Une seule connexion WebSocket persistante reçoit tous les prix
- Supporte 40-50 instances sans rate limit
- REST uniquement pour ordres et compte
- **Alternative écartée** : Polling REST — rejeté car consomme trop de rate limit

### [2026-03-11] Circuit breaker sur erreurs API consécutives
- Seuil : 10 erreurs consécutives
- Action : Arrêt d'urgence de toutes les instances
- **Pourquoi** : Empêche le bot de trader dans un état inconnu

### [2026-03-11] Capital par niveau calculé une seule fois à l'init
- Évite l'effet "Shrinking Orders"
- Utilise `get_available_capital()` (libre) pas `get_current_capital()` (total)
- Minimum 5€ par niveau, maximum configurable

### [2026-04-01] Workflow multi-agents (NOUVEAU)
- Kimi K2.5 = Architecte + Orchestrateur (ne code jamais directement)
- Claude Code = Coding principal (via OpenClaw sessions_spawn)
- Claude Opus = Review sécurité/logique (via sessions_spawn)
- Gemini = Review performance/API (via OpenRouter ou externe)
- **Convention** : Tout code passe par reviews avant validation

## Conventions établies

### Nommage
- Modules : snake_case (ex: `order_executor.py`)
- Classes : PascalCase (ex: `OrderExecutor`)
- Méthodes privées : `_prefix` (ex: `_calculate_sl_price`)
- Constants : UPPER_SNAKE_CASE dans les dataclasses

### Structure des classes
- Thread-safety : `RLock` pour réentrant, `Lock` pour simple
- Singletons : pattern avec `_lock` global et `_instance`
- Dataclasses avec `slots=True` pour performance

### Gestion des erreurs
- Jamais de stack trace exposée dans les réponses API
- Logs en langage humain pour événements critiques
- Valeurs par défaut fail-safe (ex: balance = 0.0 si erreur)
- Try/except avec `logger.exception()` dans tous les callbacks

### Sécurité API
- Clés Kraken uniquement via variables d'environnement
- Jamais hardcodées, jamais dans GitHub
- Format symboles : `XXBTZEUR` (pas BTC/EUR)

## Bugs connus et solutions

### [CORRIGÉ] WebSocket crash sur données liste
- **Problème** : `isinstance(data, dict)` manquait avant accès clé
- **Solution** : Vérification type avant traitement

### [CORRIGÉ] Capital allocation drift
- **Problème** : `get_current_capital()` utilisé au lieu de `get_available_capital()`
- **Solution** : Recalcul explicite avec `recalculate_allocated_capital()`

### [CORRIGÉ] Race conditions multi-threads
- **Problème** : Accès concurrents aux positions
- **Solution** : `RLock` sur toutes les méthodes accédant à l'état

### [CONTROVERSÉ] Sélection auto "meilleur marché"
- **État** : Implémenté mais déconseillé par Gemini + Opus
- **Risque** : Winner-take-all expose à la concentration
- **Décision** : À remplacer par "régime-based exclusion"

## Prochaines tâches prioritaires

### 1. Modules Phase 1 — Performance de base
- [ ] **ATR Filter** : Pause Grid si volatilité hors plage 2-8% (codé, corrections en attente)
- [x] **Kelly Criterion Sizing** : Taille de position optimale selon PF historique ✅
- [x] **Régime de marché** : Détection range/trend/crise avec pause auto ✅
- [x] **Funding Rates** : Surveillance temps réel, pause si extrême ✅
- [ ] **Open Interest** : Détection squeeze potentiel 🔨 EN COURS

### 2. Shadow Trading
- [ ] Instance paper trading en parallèle du live
- [ ] Validation PF > 1.5 avant transfert capital
- [ ] Durées : crypto 2sem, forex 3sem, commodités 4sem

### 3. Dashboard enrichi
- [ ] PF global et par instance en temps réel
- [ ] Drawdown tracking
- [ ] État stratégies dormantes
- [ ] Résumé quotidien automatique

### 4. Stratégies dormantes
- [ ] Mean Reversion + Order Flow
- [ ] Arbitrage Triangulaire

## Modules et leur état

| Module | État | Fichier |
|--------|------|---------|
| Grid Strategy | ✅ Actif | `strategies/grid.py` |
| Trend Strategy | ✅ Actif | `strategies/trend.py` |
| Orchestrator | ✅ Actif | `orchestrator.py` |
| OrderExecutor | ✅ Actif | `order_executor.py` |
| StopLossManager | ✅ Actif | `stop_loss_manager.py` |
| ReconciliationManager | ✅ Actif | `reconciliation.py` |
| RiskManager | ✅ Actif | `risk_manager.py` |
| AutoEvolutionManager | ✅ Actif | `auto_evolution.py` |
| MarketSelector | ⚠️ Controversé | `market_selector.py` |
| Dashboard API | ✅ Actif | `api/dashboard.py` |
| Kelly Criterion | ✅ Actif | `modules/kelly_criterion.py` |
| Mean Reversion | 🔒 Dormant | À créer |
| Arbitrage | 🔒 Dormant | À créer |

## Paramètres critiques

```python
# Grid
GRID_RANGE_PERCENT = 7.0          # +/- 7% autour du prix central
GRID_NUM_LEVELS = 15              # Nombre de niveaux
GRID_MIN_THRESHOLD = 1.5          # Seuil de vente minimum (couvre frais)
GRID_MAX_DRAWDOWN = 10.0          # Stop-loss niveau

# Risk
MAX_INSTANCES = 5                 # Limite sécurité (objectif 50)
MAX_LEVERAGE = 3                  # Plafond absolu
CIRCUIT_BREAKER_ERRORS = 10       # Erreurs avant arrêt

# Sélection marché
MAX_SAME_MARKET_INSTANCES = 2     # Max 2 instances par paire
MIN_QUALITY_SCORE = 40            # Score composite minimum
MIN_DIVERSIFICATION = 3           # Min 3 marchés différents
```

## Notes de sécurité

- **Paper trading** : Toujours isolé du live (flags séparés)
- **Dashboard** : Jamais de endpoints POST modifiant l'état (sauf emergency-stop avec confirmation)
- **Levier** : Configurable uniquement manuellement, jamais auto-adaptatif sans validation
- **Disjoncteur** : Seuil de perte globale configurable sans toucher au code

## Historique des reviews

- **2026-03-11** : Review Gemini + Opus finale — SAFE_FOR_TESTING après corrections
- **2026-03-11** : Controverse sur sélection auto marchés — recommandation : revenir à approche conservative
