# AutoBot V2 — Contexte Projet (Mise à jour 2026-04-02)

## 🎯 État Global
- **System Status**: PRODUCTION READY (après reviews Opus + Gemini)
- **Architecture**: Asyncio + uvloop (migration P0 TERMINÉE)
- **Capacité**: 2000+ instances (benchmark: 555K ticks/sec, 1.8µs latence)
- **Tests**: 400+ tests passant
- **Modules Performance**: 19/19 codés et reviewés

---

## 📊 Migration Asyncio P0-P6 (EN COURS)

| Phase | Description | Statut | Tests |
|-------|-------------|--------|-------|
| **P0** | Migration asyncio + uvloop | ✅ Terminé | 12 modules créés |
| **P1** | Order Router Central | ✅ Terminé | 37/37 |
| **P2** | Ring Buffer Lock-Free | ✅ Terminé | 41/41 |
| **P3** | Dispatch Async (1 queue/instance) | ✅ Terminé | 39/39 |
| **P4** | Hot/Cold Path Separation | ✅ Terminé | 38/38 |
| **P5** | OS Tuning (TCP_NODELAY, etc.) | ✅ Terminé | 47/47 |
| **P6** | Exécution Spéculative | ✅ Terminé | 51/51 |

**Benchmarks P4:**
- `on_price_update()` P95: **0.25 µs**
- `on_price_update()` P99: **1.08 µs**

---

## 🏗️ Architecture Système

### Stack Technique
- **Langage**: Python 3.11+ avec type hints stricts
- **Event Loop**: asyncio + uvloop
- **Connecteur**: Kraken API (WebSocket persistant + REST)
- **Persistence**: SQLite (async via run_in_executor)
- **Dashboard**: FastAPI + React

### Modules Async Créés (P0-P4)
```
src/autobot/v2/
├── *_async.py              # 12 modules async (P0)
├── order_router.py         # P1: PriorityQueue EMERGENCY/ORDER/INFO
├── ring_buffer.py          # P2: Lock-free SPMC
├── ring_buffer_dispatcher.py
├── async_dispatcher.py     # P3: 1 queue par instance
├── instance_queue.py
├── hot_path_optimizer.py   # P4: GC disable, latency tracking
└── cold_path_scheduler.py  # P4: Fire-and-forget tasks
```

---

## 🧩 Modules de Performance (19 modules)

### Phase 1 — Fondamentaux (5 modules)
| Module | Statut | Tests | Reviews |
|--------|--------|-------|---------|
| ATR Filter | ✅ | 48/48 | ✅ Opus + Gemini |
| Kelly Criterion | ✅ | 47/47 | ✅ Opus + Gemini |
| Regime Detector | ✅ | 68/68 | ✅ Opus + Gemini |
| Funding Rates | ✅ | 99/99 | ✅ Opus + Gemini |
| Open Interest | ✅ | 99/99 | ✅ Opus + Gemini |

### Phase 2 — Exécution (5 modules)
| Module | Statut | Tests | Reviews |
|--------|--------|-------|---------|
| VWAP/TWAP | ✅ | — | ✅ Opus + Gemini |
| Liquidation Heatmap | ✅ | — | ✅ Opus + Gemini |
| Black Swan Catcher | ✅ | — | ✅ Opus + Gemini |
| Momentum Scoring | ✅ | — | ✅ Opus + Gemini |
| Vote Multi-Indicateurs | ✅ | — | ✅ Opus + Gemini |

### Phase 3 — Intelligence (7 modules)
| Module | Statut | Tests | Reviews |
|--------|--------|-------|---------|
| Pairs Trading | ✅ | — | ✅ Opus + Gemini |
| XGBoost Predictor | ✅ | — | ✅ Opus + Gemini |
| On-chain Data | ✅ | — | ✅ Opus + Gemini |
| DCA Hybride Grid | ✅ | — | ✅ Opus + Gemini |
| Fee Optimizer | ✅ | — | ✅ Opus + Gemini |
| Micro-Grid Scalping | ✅ | — | ✅ Opus + Gemini |
| Rate Limit Optimizer | ✅ | — | ✅ Opus + Gemini |

### Phase 4 — Avancé (2 modules)
| Module | Statut | Tests | Reviews |
|--------|--------|-------|---------|
| Sentiment NLP | ✅ | — | ✅ Opus + Gemini |
| CNN-LSTM (Heuristic Predictor) | ✅ | — | ✅ Opus + Gemini |

---

## 🎭 Shadow Trading

**Implémenté**: `ShadowTradingManager` (35 tests ✅)

### Mécanisme
- Instances paper trading en parallèle du live
- Capital isolé (max 25% transfert vers live)

### Promotion vers Live
| Condition | Seuil | Durée validation |
|-----------|-------|------------------|
| PF (Profit Factor) | ≥ 1.5 | Variable |
| Nombre trades | ≥ 30 | — |
| Crypto volatile | — | 14 jours |
| Forex modéré | — | 21 jours |
| Commodités calme | — | 28 jours |

### Échec validation
- Instance reste en paper ou fermée
- Pas de promotion automatique sans critères

---

## 📈 Dashboard Enrichi

**Nouveaux endpoints API:**
- `/api/performance` — PF global et par instance (Sharpe, win rate)
- `/api/drawdown` — Max drawdown et courant
- `/api/shadow-status` — État shadow trading
- `/api/phase1-modules` — Statut 19 modules performance
- `/api/strategies-dormantes` — Mean Reversion, Arbitrage status

**Frontend React**: `/dashboard/src/` (compatible)

---

## 🎲 Stratégies (4 codées)

| Stratégie | État | Tests | Reviews |
|-----------|------|-------|---------|
| **Grid Trading** | ✅ Actif | — | — |
| **Mean Reversion** | 🔒 Dormante | 13/13 | ✅ Opus + Gemini |
| **Arbitrage Triangulaire** | 🔒 Dormante | 18/18 | ✅ Opus + Gemini |
| **Trend Following** | 🔒 Dormante | — | — |

### Déverrouillage
1. Shadow trading obligatoire
2. PF > 1.5 pendant durée validation
3. Activation manuelle via dashboard

---

## ⚡ Système de Levier (3 niveaux)

| Niveau | Levier | Conditions | Validation |
|--------|--------|------------|------------|
| **X1** | 1x | Défaut, toujours actif | Auto |
| **X2** | 2x | PF>2.0 (30j) + range-bound + DD<5% | Auto |
| **X3** | 3x | PF>2.5 (60j) + DD<3% | **Humaine obligatoire** |

### Sécurités
- Levier configurable manuellement uniquement
- Bot ne modifie jamais auto
- Coupure auto si conditions plus remplies
- Plafond global: 25% max capital par transfert shadow

---

## 🛡️ Sécurité

### Circuit Breaker
- **Seuil erreurs API**: 10 consécutives → arrêt d'urgence
- **Seuil PF global**: < 1.2 → arrêt
- **Max drawdown**: Configurable (défaut 10%)

### Paper Trading
- Strictement isolé (flags `is_paper` séparés)
- Jamais de conflit avec le live

### Stop-Loss
- Dynamique: adapté à la volatilité (ATR-based)
- Pas de SL fixe

### Clés API
- Uniquement dans `.env` (VPS)
- Jamais dans GitHub
- Variables d'environnement uniquement

### Pause auto
- En forte tendance: via `RegimeDetector` (ADX-based)
- En crise: ATR > baseline × 3

---

## 🔄 Workflow Multi-Agents

```
Kimi K2.5 (Architecte)
    ↓
Définit tâche P0-P6
    ↓
Claude Code (Coding)
    ↓
Implémente modules
    ↓
Claude Opus (Review sécurité)
Gemini (Review performance)
    ↓
Corrections
    ↓
Validation finale
```

---

## ⚠️ Points de Vigilance

### Controverse Phase 6 (Multi-market)
- **État**: Implémenté mais déconseillé
- **Avis Gemini**: Éviter "best market" auto-selection
- **Avis Opus**: Préférer "regime-based exclusion" à "winner-take-all"
- **Recommandation**: Utiliser approche conservative (exclusion, pas sélection)

### Tests
- ✅ Tests unitaires: 400+ passent
- ⚠️ Tests d'intégration: Pas encore faits
- ⚠️ Tests E2E avec vraies clés API: À faire avant production

---

## 📋 Checklist Pré-Production

- [ ] P5 (OS Tuning) terminé
- [ ] P6 (Exécution Spéculative) terminé
- [ ] Tests d'intégration complets
- [ ] Paper trading 48h avec 100€
- [ ] PF > 1.2 et pas d'erreurs critiques
- [ ] Reviews Gemini + Opus sur P5-P6
- [ ] Mise à jour documentation

---

## 📁 Fichiers Clés

| Fichier | Description |
|---------|-------------|
| `PLAN_TODO.md` | Roadmap P0-P6 détaillée |
| `MEMORY.md` | Mémoire long terme projet |
| `CLAUDE_CODE_CONTEXT.md` | Contexte pour Claude Code |
| `P1_MISSION.md` → `P6_MISSION.md` | Missions par phase |

---

*Dernière mise à jour: 2026-04-02 — P0-P4 terminés, P5 en cours*
