# 🏗️ VALIDATION TECHNIQUE — AUTOBOT V2 FULL AUTO
## Rapport d'architecture multi-instance avec validation "Voyants au Vert"
**Date :** 2026-03-10  
**Basé sur :** Code existant (1400 LOC, 4 modules) + Audit V1 + Spécifications V2  
**Méthodologie :** Analyse code source, documentation Kraken API, contraintes techniques réelles

---

# 📊 SYNTHÈSE EXÉCUTIVE

| Critère | Verdict | Note |
|---------|---------|------|
| **Faisabilité globale** | 🟢 Faisable | Architecture réaliste, patterns connus |
| **Complexité** | 🟡 Significative | ~8-12 semaines dev pour un développeur |
| **Risques financiers** | 🟡 Maîtrisables | Avec les sécurités proposées |
| **Contraintes API** | 🟡 Gérables | Nécessite WebSocket + pool intelligent |
| **Base existante** | 🟡 Réutilisable à 40% | Refactoring nécessaire pour multi-instance |

**Verdict global : 🟢 Le projet est techniquement faisable mais représente un saut de complexité majeur par rapport à V1.**

---

# 1. FAISABILITÉ TECHNIQUE DÉTAILLÉE

## 1.1 Multi-instances sans limite

### Verdict : 🟢 Faisable

**Architecture recommandée :**
```
Orchestrator (singleton)
  ├── InstanceManager
  │     ├── Instance #1 (Grid, 500€)    → own state, own strategy
  │     ├── Instance #2 (Trend, 1500€)  → own state, own strategy
  │     └── Instance #N (Arb, 2000€)    → own state, own strategy
  ├── ValidatorEngine (shared)
  ├── MarketDataService (shared, single WebSocket)
  └── KrakenAPIPool (shared, rate-limit aware)
```

**Points clés :**
- ✅ **Pas de limite hardcodée** : Le Validator Engine fait office de gatekeeper naturel. Si les conditions ne sont pas réunies → pas de nouvelle instance. Cela crée une auto-limitation organique.
- ✅ **Indépendance des instances** : Chaque instance encapsule sa stratégie, son capital, ses positions. Pattern classique Actor/Worker.
- ✅ **Shared services** : MarketData et API pool sont mutualisés (critique pour les rate limits).
- ⚠️ **Partage API key** : Toutes les instances partagent la même clé API Kraken → le rate limiting est GLOBAL. C'est la contrainte n°1.

**Limites réelles (non hardcodées mais imposées par Kraken) :**
- Max 60-225 ordres ouverts par paire (selon tier)
- Rate counter partagé entre toutes les instances
- Avec 10 instances actives, chacune est limitée à ~6-22 ordres ouverts par paire

### Risques spécifiques :
| Risque | Probabilité | Impact | Mitigation |
|--------|-------------|--------|------------|
| Race condition sur le capital | 🟡 Moyenne | 🔴 Élevé | Mutex/lock sur allocation capital |
| API rate limit dépassé | 🟡 Moyenne | 🟡 Moyen | Pool centralisé avec queue |
| Memory leak (instances zombies) | 🟢 Faible | 🟡 Moyen | Garbage collector d'instances |

---

## 1.2 Validator Engine ("Voyants au Vert")

### Verdict : 🟢 Faisable (pattern classique)

**Architecture proposée :**
```python
class ValidatorEngine:
    """
    Chaque action passe par validate() avant exécution.
    Retourne un ValidationResult avec statut et détails.
    """
    
    def validate(self, action: Action, context: InstanceContext) -> ValidationResult:
        checks = self.get_checks_for_action(action.type)
        results = [check.evaluate(context) for check in checks]
        
        return ValidationResult(
            passed=all(r.passed for r in results),
            checks=results,  # détail de chaque voyant
            action=action
        )
```

**Matrice de validation par action :**

| Check \ Action | Spin-off | Levier x2 | Modif TP/SL | Ouverture pos |
|----------------|----------|-----------|-------------|----------------|
| Capital suffisant | ✅ ≥2000€ | ✅ ≥1000€ | — | ✅ Solde OK |
| Historique positif | ✅ 5+ trades | ✅ 5 consec. | — | — |
| Volatilité OK | ✅ <10%/24h | ✅ pas extrême | ✅ recalc. | ✅ dans range |
| Drawdown OK | — | ✅ <10% | — | — |
| Max positions | — | — | — | ✅ <10/inst |
| Pas de crise | ✅ | ✅ | — | ✅ |
| Tendance claire | — | ✅ | ✅ détectée | Selon strat. |
| Pas d'ordre existant | — | — | — | ✅ ce niveau |

**Complexité :** ⭐⭐ Moyenne
- Chaque check est une pure function (testable, composable)
- Le pattern est un Chain of Responsibility / Specification pattern
- L'ajout de nouveaux checks est trivial (plugin-like)

**Données requises pour les checks :**
| Donnée | Source | Fréquence |
|--------|--------|-----------|
| Prix courant | WebSocket ticker | Temps réel |
| Volatilité 24h | REST OHLC ou calcul local | Toutes les 15 min |
| Balance/Capital | REST Balance | Avant chaque action |
| Historique trades | StateManager local | Cache local |
| Drawdown | Calcul local | Continu |
| Ordres ouverts | WebSocket executions | Temps réel |

---

## 1.3 Stratégies Adaptatives

### Verdict : 🟢 pour Grid & Trend, 🟡 pour Arbitrage/Breakout

| Stratégie | Verdict | Justification |
|-----------|---------|---------------|
| **Grid Classique** (100€+) | 🟢 Faisable | Déjà implémenté à 80% dans V1 |
| **Grid Adaptatif** (500€+) | 🟢 Faisable | Extension du Grid existant + recalcul range |
| **Trend Following** (500€+) | 🟢 Faisable | RSI/MACD standard, librairies dispo (ta-lib) |
| **Breakout** (1000€+) | 🟡 Difficile | Détection niveaux clés fiable = complexe |
| **Arbitrage** (1000€+) | 🟡 Difficile | Inter-exchange = 2ème API + latence problème |

**Pattern Strategy recommandé :**
```python
class Strategy(ABC):
    @abstractmethod
    def analyze(self, market_data: MarketData) -> Signal:
        """Retourne BUY/SELL/HOLD avec confidence score"""
    
    @abstractmethod
    def get_tp_sl(self, capital: float) -> Tuple[float, float]:
        """TP/SL dynamiques selon capital"""
    
    @classmethod
    def for_capital(cls, capital: float) -> 'Strategy':
        """Factory: sélection auto selon capital"""
        if capital >= 1000:
            return BreakoutStrategy()  # ou TrendFollowing
        elif capital >= 500:
            return TrendFollowingStrategy()
        else:
            return GridStrategy()
```

**⚠️ Avertissement sur l'arbitrage :**
- L'arbitrage inter-exchange nécessite une 2ème API (Binance, Coinbase...)
- La latence réseau rend l'arbitrage crypto très compétitif
- Les frais de transfert inter-exchange peuvent annuler les gains
- **Recommandation : Reporter l'arbitrage à une phase ultérieure**

---

## 1.4 Check Intervalle 15-30 minutes

### Verdict : 🟢 Faisable et bien dimensionné

**Analyse des rate limits Kraken (données réelles) :**

| Tier | REST API Counter Max | Decay rate | Trading Counter Max | Trading Decay |
|------|---------------------|------------|---------------------|---------------|
| Starter | 15 | -0.33/sec | 60/pair | -1/sec |
| Intermediate | 20 | -0.5/sec | 125/pair | -2.34/sec |
| Pro | 20 | -1/sec | 180/pair | -3.75/sec |

**Budget API par cycle de 15 min (tier Intermediate) :**
- REST counter : 20 max, decay 0.5/sec → en 15 min, budget ≈ 20 + (900 × 0.5) = **470 appels** théoriques (mais burst limité à 20)
- En pratique avec burst : ~20 appels rapides, puis 1 appel/2 sec max
- Trading counter : 125 max, decay 2.34/sec → très large pour notre usage

**Budget par instance par cycle (5 instances, tier Intermediate) :**
```
Appels REST nécessaires par instance par cycle :
  - Balance check        : 1 appel  (cost 1)
  - Ticker prix          : 0 appels (WebSocket)
  - OHLC volatilité      : 1 appel  (cost 1) [ou cache]
  - Check ordres ouverts : 0 appels (WebSocket)
  - Place order (si signal) : 1 appel (trading counter, pas REST)
  ──────────────────────
  Total REST/instance    : ~2 appels/cycle
  Total 5 instances      : ~10 appels/cycle ✅ largement dans les limites
```

**Architecture recommandée :**
```
┌─────────────────────────────────────┐
│       SCHEDULER (APScheduler)       │
│  - Cycle principal : 15-30 min      │
│  - Ajuste selon volatilité          │
│  - Séquence : Instance par instance │
│  - Espacement : 5-10 sec entre inst │
└─────────────┬───────────────────────┘
              │
    ┌─────────▼──────────┐
    │  API RATE LIMITER  │
    │  - Token bucket    │
    │  - Queue priorité  │
    │  - Tracking counter│
    └────────────────────┘
```

**Ajustement dynamique proposé :**
```python
def calculate_interval(volatility_24h: float) -> int:
    """Retourne l'intervalle en minutes."""
    if volatility_24h > 8.0:       # Très volatile
        return 15
    elif volatility_24h > 4.0:     # Modéré
        return 20
    else:                           # Calme
        return 30
```

**⚠️ Recommandation critique : WebSocket obligatoire**
- Les données de prix et d'ordres DOIVENT passer par WebSocket
- Le REST doit être réservé aux actions (place order, get balance)
- Cela réduit la consommation REST de ~80%

---

## 1.5 Gestion "Voyant Rouge"

### Verdict : 🟢 Faisable (State Machine)

**Machine à états proposée :**
```
                    ┌────────────────┐
         ┌─────────│    NORMAL      │
         │         │  (tous verts)  │
         │         └───────┬────────┘
         │                 │ 1 check rouge
         │         ┌───────▼────────┐
         │         │    WATCHFUL    │
         │ Reset   │  (1-2 rouges)  │──────┐
         │ (3 verts│  Passif, retry │      │
         │  consec)│  1h interval   │      │ 3 rouges consec.
         │         └───────┬────────┘      │ OU drawdown >15%
         │                 │               │
         │         ┌───────▼────────┐      │
         │         │    ALERT       │◀─────┘
         └─────────│  Contre-mesure │
                   │  active        │
                   └────────────────┘
```

**Actions par état :**

| État | Intervalle check | Actions autorisées | Contre-mesures |
|------|------------------|--------------------|----------------|
| NORMAL | 15-30 min | Toutes | Aucune |
| WATCHFUL | 60 min | Aucune nouvelle | Log + alerte |
| ALERT | 5 min | Fermeture uniquement | Cancel ordres, SL urgence, pause |

**Transitions :**
```python
class RiskStateMachine:
    def evaluate(self, instance: Instance) -> RiskState:
        red_checks = instance.consecutive_red_checks
        drawdown = instance.current_drawdown_percent
        
        if red_checks >= 3 or drawdown > 15.0:
            return RiskState.ALERT
        elif red_checks >= 1:
            return RiskState.WATCHFUL
        else:
            return RiskState.NORMAL
    
    def execute_countermeasures(self, instance: Instance):
        """Mode ALERT : actions défensives"""
        # 1. Cancel tous les ordres en attente
        instance.cancel_all_pending_orders()
        # 2. Si drawdown > 20% : fermeture forcée
        if instance.current_drawdown_percent > 20.0:
            instance.emergency_close_all()
        # 3. Passage en mode pause
        instance.trading_enabled = False
        # 4. Alerte
        instance.alert("VOYANT ROUGE - Contre-mesures activées")
```

---

# 2. COMPLEXITÉ ET TEMPS DE DÉVELOPPEMENT

## 2.1 Inventaire des composants à développer

| Composant | LOC estimées | Complexité | Dépend de | Durée estimée |
|-----------|-------------|------------|-----------|---------------|
| **Orchestrator** | 300-500 | ⭐⭐⭐ | Tous | 1 semaine |
| **ValidatorEngine** | 400-600 | ⭐⭐ | MarketData | 1 semaine |
| **InstanceManager** | 300-400 | ⭐⭐ | StateManager | 3-4 jours |
| **StateManager (SQLite)** | 400-500 | ⭐⭐ | — | 3-4 jours |
| **WebSocket Client** | 300-400 | ⭐⭐⭐ | — | 1 semaine |
| **API Rate Limiter** | 200-300 | ⭐⭐ | — | 2-3 jours |
| **Strategy Framework** | 500-700 | ⭐⭐⭐ | MarketData | 1.5 semaines |
| **Grid Strategy** (refactor) | 200 | ⭐ | Existant | 2 jours |
| **Trend Following** | 300-400 | ⭐⭐ | Indicateurs | 3-4 jours |
| **Breakout** | 300-400 | ⭐⭐⭐ | Indicateurs | 4-5 jours |
| **Risk Manager** | 300-400 | ⭐⭐ | StateManager | 3-4 jours |
| **TP/SL Dynamique** | 200-300 | ⭐⭐ | Risk Manager | 2-3 jours |
| **Levier Manager** | 200-250 | ⭐⭐ | Validator | 2 jours |
| **Config System** | 150-200 | ⭐ | — | 1 jour |
| **main.py + CLI** | 150-200 | ⭐ | Orchestrator | 1 jour |
| **Tests unitaires** | 800-1200 | ⭐⭐ | Tous | 1.5 semaines |
| **Tests intégration** | 400-600 | ⭐⭐⭐ | Tous | 1 semaine |
| **Dashboard (basique)** | 300-500 | ⭐⭐ | Orchestrator | 3-4 jours |
| **Alertes/Notifications** | 200-300 | ⭐⭐ | — | 2 jours |
| **TOTAL** | **~5000-7000** | — | — | **~8-12 semaines** |

## 2.2 Réutilisabilité du code V1

| Module V1 | LOC | Réutilisable ? | Modifications nécessaires |
|-----------|-----|----------------|--------------------------|
| `grid_calculator.py` | 147 | ✅ 90% | Adapter pour multi-instance (plus de singleton) |
| `order_manager.py` | 500 | ✅ 70% | Ajouter support WebSocket, lever les constantes hardcodées |
| `position_manager.py` | 529 | ✅ 60% | Refactor pour scope instance, ajouter gestion ordres partiels |
| `error_handler.py` | 211 | ✅ 95% | Quasi intact, ajouter métriques |

**Conclusion : ~40% du code V1 est directement réutilisable**, le reste nécessite un refactoring significatif pour supporter le multi-instance.

---

# 3. RISQUES IDENTIFIÉS

## 3.1 Risques Techniques

| # | Risque | Probabilité | Impact | Sévérité | Mitigation |
|---|--------|-------------|--------|----------|------------|
| T1 | **Race condition capital** entre instances | 🔴 Haute | 🔴 Critique | 🔴 | Mutex global sur allocations + double-check |
| T2 | **WebSocket disconnect** pendant trading actif | 🔴 Haute | 🟡 Moyen | 🟡 | Reconnect auto + fallback REST + state recovery |
| T3 | **Rate limit Kraken** avec N instances | 🟡 Moyenne | 🟡 Moyen | 🟡 | Pool centralisé + queue prioritaire |
| T4 | **State corruption** (crash pendant écriture) | 🟡 Moyenne | 🔴 Critique | 🔴 | WAL mode SQLite + transactions atomiques |
| T5 | **Memory leak** instances jamais nettoyées | 🟢 Faible | 🟡 Moyen | 🟢 | GC périodique + monitoring mémoire |
| T6 | **Indicateurs techniques incorrects** | 🟡 Moyenne | 🟡 Moyen | 🟡 | Tests approfondis + validation croisée |

## 3.2 Risques Financiers

| # | Risque | Probabilité | Impact | Sévérité | Mitigation |
|---|--------|-------------|--------|----------|------------|
| F1 | **Flash crash** → toutes instances SL simultané | 🟢 Faible | 🔴 Critique | 🟡 | Diversification stratégies + circuit breaker global |
| F2 | **Levier x2** amplifie les pertes | 🟡 Moyenne | 🟡 Moyen | 🟡 | Conditions très strictes (5 wins consec. + drawdown <10%) |
| F3 | **Spin-off excessif** dilue le capital | 🟢 Faible | 🟡 Moyen | 🟢 | Validator Engine + seuil 2000€ |
| F4 | **Frais cumulés** N instances × M trades | 🟡 Moyenne | 🟡 Moyen | 🟡 | Calcul frais dans chaque décision, maker preferred |
| F5 | **Corrélation non détectée** entre instances | 🟡 Moyenne | 🟡 Moyen | 🟡 | Si toutes sur BTC → même risque. Diversifier les paires |

## 3.3 Risques Opérationnels

| # | Risque | Probabilité | Impact | Sévérité | Mitigation |
|---|--------|-------------|--------|----------|------------|
| O1 | **Serveur down** → positions orphelines | 🟡 Moyenne | 🔴 Critique | 🔴 | State persistence + recovery au restart + SL sur Kraken |
| O2 | **API Kraken indisponible** (maintenance) | 🟡 Moyenne | 🟡 Moyen | 🟡 | Mode pause auto + retry |
| O3 | **Changement API Kraken** breaking change | 🟢 Faible | 🟡 Moyen | 🟢 | Abstraction layer + versioning |

### ⚠️ Risque critique : SL côté serveur (pas côté bot)
**Le SL DOIT être posé sur Kraken comme ordre conditionnel**, pas calculé localement. Si le bot crash, les SL locaux sont perdus. Kraken supporte les ordres stop-loss natifs — les utiliser systématiquement.

---

# 4. CONTRAINTES TECHNIQUES API KRAKEN

## 4.1 Rate Limits — Analyse complète

### REST API (données vérifiées mars 2026)
```
┌─────────────────────────────────────────────────────┐
│               REST API COUNTER                       │
│                                                      │
│  Tier Intermediate (recommandé minimum) :            │
│  • Max counter : 20                                  │
│  • Decay : 0.5/sec (1 appel récupéré toutes les 2s)│
│  • Budget soutenu : 1 appel/2 sec = 30 appels/min  │
│                                                      │
│  Tier Pro (idéal) :                                  │
│  • Max counter : 20                                  │
│  • Decay : 1/sec = 60 appels/min soutenu            │
│                                                      │
│  ⚠️ AddOrder/CancelOrder = compteur SÉPARÉ          │
│  (Trading Engine limits, pas REST counter)           │
└─────────────────────────────────────────────────────┘
```

### Trading Engine (ordres)
```
┌──────────────────────────────────────────────────────┐
│           TRADING ENGINE COUNTER (par paire)          │
│                                                       │
│  Tier Intermediate :                                  │
│  • Max counter : 125 par paire                        │
│  • Decay : 2.34/sec                                   │
│  • AddOrder = +1 (fixe)                               │
│  • CancelOrder = +1 à +8 (selon âge de l'ordre)      │
│  • Cancel rapide (<5s) = +8 ← CHER                   │
│  • Cancel lent (>300s) = +0 ← GRATUIT                │
│                                                       │
│  → Favoriser les ordres qui restent longtemps         │
│  → Éviter le cancel/replace rapide                    │
└──────────────────────────────────────────────────────┘
```

### Ordres ouverts simultanés
```
Starter       : 60 par paire
Intermediate  : 80 par paire  
Pro           : 225 par paire

→ Avec 10 instances × 10 positions = 100 ordres max
→ Tier Intermediate (80) INSUFFISANT pour 10 instances !
→ Tier Pro (225) OK, ou réduire positions/instance
```

## 4.2 WebSocket — Obligatoire

| Feature | REST | WebSocket | Recommandation |
|---------|------|-----------|----------------|
| Prix temps réel | ❌ Polling coûteux | ✅ Push gratuit | **WebSocket** |
| Statut ordres | 1 appel REST | ✅ Push gratuit | **WebSocket** |
| Balance | 1 appel REST | ❌ Non dispo | **REST (cache 5 min)** |
| Place order | 1 appel REST | ✅ Possible | **WebSocket (préféré)** |
| Cancel order | 1 appel REST | ✅ Possible | **WebSocket** |
| OHLC/Historique | 1 appel REST | ❌ Non dispo | **REST (cache 15 min)** |

**Budget REST résiduel avec WebSocket :**
- Seuls Balance et OHLC restent en REST
- ~2-4 appels REST par cycle de 15 min (toutes instances)
- Très confortable même en Starter tier

## 4.3 Recommandation Tier Kraken

| Scénario | Tier recommandé | Justification |
|----------|----------------|---------------|
| 1-3 instances | Intermediate | 80 ordres/paire suffisant |
| 4-10 instances | **Pro** | 225 ordres/paire nécessaire |
| 10+ instances | Pro + optimisation | Pool ordres + rotation paires |

---

# 5. OPTIMISATIONS SUGGÉRÉES

## 5.1 Architecture

| # | Optimisation | Impact | Effort | Priorité |
|---|-------------|--------|--------|----------|
| A1 | **WebSocket unique** pour toutes les instances | 🟢 -80% appels REST | ⭐⭐ | 🔴 Critique |
| A2 | **Event-driven** au lieu de polling | 🟢 Réactivité + efficacité | ⭐⭐⭐ | 🟡 Haute |
| A3 | **SQLite WAL mode** pour persistence | 🟢 Crash-safe + performances | ⭐ | 🔴 Critique |
| A4 | **asyncio** partout (pas de threads) | 🟢 Scalabilité | ⭐⭐ | 🟡 Haute |

## 5.2 Trading

| # | Optimisation | Impact | Effort | Priorité |
|---|-------------|--------|--------|----------|
| T1 | **SL côté Kraken** (ordres conditionnels) | 🟢 Sécurité crash-proof | ⭐ | 🔴 Critique |
| T2 | **Maker-only orders** (frais 0.16% vs 0.26%) | 🟢 -38% frais | ⭐ | 🟡 Haute |
| T3 | **Cancel lent** (attendre >300s pour cancel gratuit) | 🟢 Rate limit optimisé | ⭐ | 🟡 Haute |
| T4 | **Diversification paires** entre instances | 🟢 Réduit corrélation | ⭐⭐ | 🟡 Haute |
| T5 | **Trailing stop-loss** au lieu de SL fixe | 🟢 Capture plus de gains | ⭐⭐ | 🟢 Moyenne |

## 5.3 Opérationnel

| # | Optimisation | Impact | Effort | Priorité |
|---|-------------|--------|--------|----------|
| O1 | **Health endpoint** (FastAPI) | 🟢 Monitoring externe | ⭐ | 🟡 Haute |
| O2 | **Métriques Prometheus** | 🟢 Dashboards Grafana | ⭐⭐ | 🟢 Moyenne |
| O3 | **Docker + docker-compose** | 🟢 Déploiement fiable | ⭐ | 🟡 Haute |
| O4 | **Telegram bot** pour alertes | 🟢 Réactivité humaine | ⭐ | 🟢 Moyenne |

## 5.4 Optimisation anti-gaspillage capital

```python
# Au lieu de réserver 500€ fixe par instance, 
# calculer le capital optimal selon la stratégie
def optimal_capital(strategy: str, market_conditions: dict) -> float:
    """
    Grid 15 niveaux × 5€ min/niveau = 75€ minimum
    Trend Following = 2-3 positions × 50€ = 150€ minimum
    → Pas besoin de 500€ pour chaque instance
    → Plus d'instances possibles avec le même capital
    """
```

---

# 6. ROADMAP RÉALISTE

## Phase 0 : Fondations (Semaine 1-2) — 🔴 CRITIQUE
```
Objectif : Base exécutable et testable

□ Refactoring multi-instance des modules existants
□ Config system (YAML + env vars)
□ StateManager (SQLite + WAL)
□ main.py + boucle principale
□ Requirements + Dockerfile
□ Tests unitaires modules existants
□ CI pipeline basique

Livrable : Bot mono-instance qui démarre, trade, persiste, redémarre
```

## Phase 1 : WebSocket + Validator (Semaine 3-4) — 🔴 CRITIQUE
```
Objectif : Temps réel + validation

□ Client WebSocket Kraken v2
  - Ticker (prix temps réel)
  - Executions (statut ordres)
  - Reconnect automatique
□ ValidatorEngine avec tous les checks
□ API Rate Limiter (token bucket)
□ SL côté Kraken (ordres conditionnels)
□ Tests d'intégration WebSocket (mock)

Livrable : Bot mono-instance avec prix temps réel et validation
```

## Phase 2 : Multi-instance + Orchestrator (Semaine 5-7) — 🟡 HAUTE
```
Objectif : N instances indépendantes

□ Orchestrator (scheduler + dispatch)
□ InstanceManager (create, destroy, monitor)
□ Capital allocation avec mutex
□ Spin-off logic (seuil 2000€ → nouvelle instance)
□ Risk State Machine (Normal → Watchful → Alert)
□ Contre-mesures automatiques
□ Tests multi-instance (scenarios concurrence)
□ Garbage collector instances mortes

Livrable : Bot multi-instance avec spin-off et gestion risque
```

## Phase 3 : Stratégies avancées (Semaine 8-9) — 🟡 HAUTE
```
Objectif : 3+ stratégies opérationnelles

□ Strategy framework (interface + factory)
□ Grid Adaptatif (recalcul range selon marché)
□ Trend Following (RSI + MACD + volume)
□ Breakout (support/résistance + volume)
□ TP/SL dynamiques selon capital et stratégie
□ Levier x2 conditionnel
□ Backtesting framework basique
□ Tests stratégies sur données historiques

Livrable : Multi-stratégie avec sélection auto selon capital
```

## Phase 4 : Production-ready (Semaine 10-12) — 🟢 IMPORTANTE
```
Objectif : Monitoring, alertes, robustesse

□ Dashboard web (FastAPI + simple HTML)
□ Alertes Telegram/Discord
□ Health checks + métriques
□ Logging structuré (JSON)
□ Graceful shutdown (SIGTERM handler)
□ Docker-compose production
□ Documentation complète
□ Tests de charge (10+ instances simulées)
□ Dry-run 2 semaines en conditions réelles

Livrable : Bot production-ready avec monitoring
```

## Timeline visuelle

```
Semaine:  1   2   3   4   5   6   7   8   9  10  11  12
          ┌───────┐
Phase 0:  │ FOUND │  Fondations + mono-instance
          └───────┘
              ┌───────┐
Phase 1:      │WS+VAL │  WebSocket + Validator
              └───────┘
                      ┌───────────┐
Phase 2:              │ MULTI-INST│  Orchestrator + multi
                      └───────────┘
                                  ┌───────┐
Phase 3:                          │STRATEG│  Stratégies avancées
                                  └───────┘
                                          ┌───────────┐
Phase 4:                                  │ PROD-READY│  Polish + deploy
                                          └───────────┘
```

**⚠️ Hypothèses :**
- 1 développeur à temps plein (ou équivalent)
- Familiarité avec Python asyncio et trading
- Tier Kraken Intermediate minimum (Pro recommandé pour >3 instances)
- Les 2 premières semaines de phase 4 incluent un dry-run obligatoire

---

# 7. ARCHITECTURE TECHNIQUE FINALE RECOMMANDÉE

```
┌─────────────────────────────────────────────────────────────────┐
│                      AUTOBOT V2 FULL AUTO                       │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                    ORCHESTRATOR                           │   │
│  │  • APScheduler (cycles 15-30 min)                        │   │
│  │  • Instance lifecycle management                          │   │
│  │  • Global risk monitoring                                 │   │
│  └──────────────┬──────────────────────┬────────────────────┘   │
│                 │                      │                         │
│  ┌──────────────▼──────┐  ┌───────────▼───────────┐            │
│  │  VALIDATOR ENGINE   │  │   RISK STATE MACHINE  │            │
│  │  • Check matrix     │  │   • NORMAL            │            │
│  │  • Per-action rules │  │   • WATCHFUL          │            │
│  │  • Pass/Fail + why  │  │   • ALERT             │            │
│  └─────────────────────┘  └───────────────────────┘            │
│                 │                                                │
│  ┌──────────────▼──────────────────────────────────────────┐   │
│  │              INSTANCE POOL (dynamic N)                   │   │
│  │                                                          │   │
│  │  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐      │   │
│  │  │ Inst #1 │ │ Inst #2 │ │ Inst #3 │ │ Inst #N │      │   │
│  │  │ Grid    │ │ Trend   │ │ Break   │ │ ...     │      │   │
│  │  │ 500€    │ │ 1200€   │ │ 2000€   │ │         │      │   │
│  │  │ BTC/EUR │ │ ETH/EUR │ │ BTC/EUR │ │         │      │   │
│  │  └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘      │   │
│  │       └───────────┼──────────┼───────────┘             │   │
│  └───────────────────┼──────────┼─────────────────────────┘   │
│                      │          │                               │
│  ┌───────────────────▼──────────▼─────────────────────────┐   │
│  │              SHARED SERVICES                            │   │
│  │                                                          │   │
│  │  ┌────────────┐ ┌────────────┐ ┌────────────────────┐  │   │
│  │  │ WebSocket  │ │ API Pool   │ │ State Manager      │  │   │
│  │  │ Client     │ │ Rate Limit │ │ (SQLite WAL)       │  │   │
│  │  │ • Ticker   │ │ • Token    │ │ • Positions        │  │   │
│  │  │ • Execut.  │ │   bucket   │ │ • Orders           │  │   │
│  │  │ • Reconnect│ │ • Queue    │ │ • Instance configs  │  │   │
│  │  └──────┬─────┘ └──────┬─────┘ │ • Profit history   │  │   │
│  │         │              │        └────────────────────┘  │   │
│  └─────────┼──────────────┼───────────────────────────────┘   │
│            │              │                                     │
│  ┌─────────▼──────────────▼───────────────────────────────┐   │
│  │                   KRAKEN API                            │   │
│  │        WebSocket v2  +  REST (balance, OHLC)            │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  MONITORING : FastAPI health + Telegram alerts + Logs    │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

---

# 8. STACK TECHNIQUE RECOMMANDÉ

| Couche | Technologie | Justification |
|--------|-------------|---------------|
| **Langage** | Python 3.11+ | Écosystème trading + asyncio mature |
| **Async** | asyncio + aiohttp | Non-bloquant, scale bien |
| **WebSocket** | websockets ou aiohttp.ws | Client Kraken WS v2 |
| **Persistence** | SQLite (WAL mode) | Léger, crash-safe, zéro config |
| **Config** | PyYAML + pydantic | Validation + type safety |
| **Scheduler** | APScheduler | Cycles configurables |
| **Indicateurs** | ta (Technical Analysis) | RSI, MACD, Bollinger |
| **API REST** | aiohttp.ClientSession | Async HTTP |
| **Dashboard** | FastAPI + Jinja2 | Simple, léger, async natif |
| **Alertes** | python-telegram-bot | Notifications push |
| **Tests** | pytest + pytest-asyncio | Standard, riche en fixtures |
| **Container** | Docker + docker-compose | Déploiement reproductible |
| **Logging** | structlog (JSON) | Parseable, filtrable |

---

# 9. CONCLUSION FINALE

## Matrice de faisabilité complète

| Spécification | Faisabilité | Complexité | Risque principal |
|---------------|-------------|------------|------------------|
| Multi-instances sans limite | 🟢 Faisable | ⭐⭐⭐ | Rate limits Kraken partagés |
| Validator "voyants au vert" | 🟢 Faisable | ⭐⭐ | Calibration des seuils |
| Spin-off à 2000€ | 🟢 Faisable | ⭐⭐ | Race condition capital |
| Levier x2 conditionnel | 🟢 Faisable | ⭐⭐ | Amplification pertes |
| TP/SL dynamiques | 🟢 Faisable | ⭐⭐ | Modification en cours de trade |
| Grid Strategy | 🟢 Faisable | ⭐ | Déjà quasi-implémenté |
| Trend Following | 🟢 Faisable | ⭐⭐ | Faux signaux indicateurs |
| Breakout | 🟡 Difficile | ⭐⭐⭐ | Détection niveaux fiable |
| Arbitrage inter-exchange | 🟡 Difficile | ⭐⭐⭐⭐ | Latence + 2ème API + frais |
| Check 15-30 min | 🟢 Faisable | ⭐ | Bien dimensionné |
| Gestion voyant rouge | 🟢 Faisable | ⭐⭐ | Calibration seuils |
| WebSocket temps réel | 🟢 Faisable | ⭐⭐ | Reconnect robuste |
| Persistence crash-safe | 🟢 Faisable | ⭐⭐ | SQLite WAL résout |

## Recommandations prioritaires

1. **🔴 OBLIGATOIRE** : WebSocket Kraken v2 — sans ça, le multi-instance est non viable (rate limits)
2. **🔴 OBLIGATOIRE** : Stop-loss côté Kraken (ordres conditionnels), pas côté bot
3. **🔴 OBLIGATOIRE** : Mutex/lock sur l'allocation capital entre instances
4. **🟡 FORTEMENT RECOMMANDÉ** : Tier Pro Kraken si >3 instances (225 ordres/paire)
5. **🟡 FORTEMENT RECOMMANDÉ** : Dry-run de 2 semaines minimum avant argent réel
6. **🟢 SUGGESTION** : Reporter l'arbitrage inter-exchange à une V3
7. **🟢 SUGGESTION** : Diversifier les paires entre instances (pas tout sur BTC/EUR)

## Verdict final

> **Le projet AUTOBOT V2 Full Auto est techniquement faisable (🟢) avec une complexité significative mais maîtrisable (🟡).** La base de code V1 fournit ~40% de réutilisabilité. Les contraintes API Kraken sont gérables avec WebSocket + pool intelligent. Le système de validation "voyants au vert" est un pattern classique bien maîtrisé. La roadmap réaliste est de **8-12 semaines** pour un développeur, avec un dry-run de 2 semaines inclus.
> 
> Le risque principal n'est pas technique mais **financier** : un bug dans le Validator Engine ou le Risk Manager peut entraîner des pertes en cascade sur toutes les instances. D'où l'importance critique des tests, du dry-run, et du SL côté Kraken.

---

*Rapport généré le 2026-03-10 par Opus SubAgent — Basé sur l'analyse du code source, l'audit V1, la documentation Kraken API, et les spécifications V2.*