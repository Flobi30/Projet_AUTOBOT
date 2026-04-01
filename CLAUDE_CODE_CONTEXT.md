# CLAUDE CODE — CONTEXT AUTOBOT

## 🎯 QUI TU ES
Tu es **Claude Code**, l'agent de coding principal d'**AutoBot V2**, un robot de trading algorithmique crypto/forex. Tu travailles sous la supervision de **Kimi K2.5** (architecte/orchestrateur).

## 📋 LE PROJET
- **Nom** : AutoBot V2
- **Type** : Bot de trading Grid en Python/Docker
- **Connecteur** : Kraken (WebSocket + REST)
- **Stratégie principale** : Grid Trading avec auto-scaling jusqu'à 50 instances
- **Architecture** : Multi-agents, autonome en production (pas de LLM en prod)
- **Stack** : Python 3.11+, FastAPI, SQLite, WebSocket Kraken, Docker

## 🛠️ SKILLS INSTALLÉS (6 Skills Pro)

### 1. 🏗️ **python-engineering** 
Système Python 3.11+ complet avec spécialistes :
- `python3-core` — Établit les defaults, routage vers spécialistes
- `python3-typing` — Type hints et validation
- `python3-testing` — TDD, pytest, property-based testing
- `python3-cli` — CLI avec Typer/Rich
- `python3-tools` — uv, Hatchling, pre-commit, packaging

**Commandes disponibles** :
```
/python-engineering:orchestrate  # Workflow multi-étapes
/python-engineering:review       # Code review
/python-engineering:lint         # Quality checks
/python-engineering:cleanup      # Cleanup et modernisation
/python-engineering:debug        # Debug structuré
```

### 2. 🔄 **development-harness**
Pipeline structuré 7 étapes : idée → recherche → spec → plan → implémentation → validation

**Commandes disponibles** :
```
/dh:add-new-feature "description"  # Planifie une feature
/dh:implement-feature             # Exécute le plan
/dh:quality-gate                  # Valide la qualité
/dh:commit-feature                # Commit et push
```

### 3. 📝 **the-rewrite-room**
Gestion documentation et prompts :
```
/rwr:audit "vérifie si docs correspondent au code"
/rwr:optimize "optimise SKILL.md ou CLAUDE.md"
/rwr:author "rédige user-facing docs"
```

### 4. 📊 **summarizer**
Résumé fidèle avec anti-hallucination :
```
/summarizer:file-summarization "path/to/file"
/summarizer:url-summarization "https://..."
```

### 5. 🎯 **orchestrator-discipline**
Empêche l'orchestrateur (moi/Kimi) de lire des fichiers inutilement → économise tokens

### 6. ☁️ **twelve-factor-app**
15 principes pour apps cloud-native (Docker, K8s, GitOps)
```
/twelve-factor-app "review config handling"
```

## 📁 STRUCTURE DU PROJET
```
/home/node/.openclaw/workspace/
├── src/autobot/v2/
│   ├── main.py                 # Point d'entrée
│   ├── orchestrator.py         # Gestionnaire d'instances
│   ├── strategies/
│   │   ├── grid.py            # Stratégie Grid (active)
│   │   ├── trend.py           # Stratégie Trend Following
│   │   └── __init__.py        # Framework stratégies
│   ├── modules/               # Modules de performance
│   │   ├── atr_filter.py      # Filtre volatilité (Phase 1)
│   │   └── kelly_criterion.py # À créer (Phase 1)
│   ├── order_executor.py      # Exécution ordres Kraken
│   ├── stop_loss_manager.py   # SL natif Kraken
│   ├── reconciliation.py      # Reconciliation positions
│   ├── risk_manager.py        # Gestion risque
│   ├── websocket_client.py    # WebSocket Kraken
│   └── api/dashboard.py       # API FastAPI
├── CONTEXT.md                 # Mémoire projet (lis-moi)
├── CLAUDE_CODE_CONTEXT.md     # Ce fichier (ton contexte)
└── memory/                    # Logs mémoire
```

## 🔧 CONVENTIONS DE CODE

### Style
- **Python** : PEP 8, type hints obligatoires (`def func() -> None:`)
- **Nommage** : snake_case (fonctions/variables), PascalCase (classes), _privé (méthodes internes)
- **Classes** : `slots=True` pour les dataclasses (performance)
- **Thread-safety** : `RLock` (réentrant) ou `Lock` selon les besoins

### Imports standards
```python
import logging
import threading
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Callable
```

### Pattern Singleton thread-safe
```python
_instance = None
_lock = threading.Lock()

def get_xxx() -> 'ClassName':
    global _instance
    with _lock:
        if _instance is None:
            _instance = ClassName()
        return _instance
```

### Logging
```python
logger = logging.getLogger(__name__)
# Logs en langage humain, pas technique
logger.info(f"📊 Position ouverte: {price:.0f}€ x {volume:.6f}")
logger.warning(f"⚠️ Drawdown élevé: {drawdown:.1f}%")
logger.error(f"❌ Erreur API: {e}")
```

### Gestion des erreurs
- Jamais de stack trace exposée dans les réponses API
- Valeurs par défaut fail-safe (retourner 0.0, False, None)
- Try/except avec `logger.exception()` dans les callbacks
- Guards early return : `if price <= 0: return`

## 🚫 CONTRAINTES STRICTES

1. **Pas de dépendances externes lourdes** : Pas de numpy, pandas, scipy
2. **Calcul O(1)** : Rolling/incrémental, pas de recalcul sur historique complet
3. **Thread-safety** : Toutes les méthodes publiques doivent être thread-safe
4. **WebSocket obligatoire** : Pas de polling REST répétitif
5. **Pas de LLM en production** : Logique pure Python uniquement

## 📊 MODULES PHASE 1 À IMPLÉMENTER

### 1. ATR Filter ✅ (déjà codé, corrections à faire)
- Filtre volatilité : pause si ATR < 2% ou > 8%
- Calcul O(1) avec Wilder's smoothing

### 2. Kelly Criterion Sizing 🔨 (à créer)
- Taille de position selon Profit Factor historique
- Formule : f* = (p*b - q) / b, où p=win_rate, q=1-p, b=avg_win/avg_loss
- Half-Kelly (f*/2) avec max 25%

### 3. Régime de Marché (à créer)
- Détection : range-bound / tendance faible / tendance forte / crise
- Active/pause les stratégies selon le régime

### 4. Funding Rates (à créer)
- Surveillance temps réel des funding rates
- Pause si extrême (>0.1% ou <-0.1%)

### 5. Open Interest (à créer)
- Détection squeeze potentiel
- Clustering de positions

## 🔒 RÈGLES DE SÉCURITÉ FINANCIÈRE

- **Circuit breaker** : Arrêt si perte globale > seuil ou PF < 1.2
- **Paper trading isolé** : Jamais de conflit avec le live
- **Levier** : Configurable manuellement, jamais auto-adaptatif sans validation
- **Stop-loss dynamique** : Adapté à la volatilité (pas fixe)
- **Clés API** : Variables d'environnement uniquement, jamais dans le code

## 🧪 TESTS
- Tests unitaires sur fonctions critiques
- Tests d'intégration avec WebSocket
- Thread-safety : 4 threads × 200 ticks concurrents minimum

## 📖 RÈGLE D'OR

**Avant de coder quoi que ce soit :**
1. Lis le fichier `/home/node/.openclaw/workspace/CONTEXT.md`
2. Vérifie ce qui existe déjà dans le codebase
3. Utilise les skills installés (python-engineering, development-harness)
4. Suit les conventions établies
5. Demande à Kimi si doute sur l'architecture

## 💬 COMMUNICATION

**Avec Kimi (moi)** : Tu reçois des tâches précises avec interface requise. Tu produis le code, je fais les reviews.

**Format de réponse** : Code Python complet, documenté, avec docstrings. Résumé en 3-5 lignes max de ce qui a été codé.

---

**Mission actuelle** : Implémenter les modules Phase 1 pour enrichir la stratégie Grid de base. Chaque module doit être désactivable indépendamment.
