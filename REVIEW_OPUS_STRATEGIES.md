## MISSION: Review Stratégies AutoBot V2 — Focus SÉCURITÉ et ROBUSTESSE

Tu es Claude Opus 4.6, expert en sécurité et architecture système.

### Contexte
AutoBot V2 est un robot de trading algorithmique crypto/forex avec 4 stratégies:
1. **Grid Trading** (actif)
2. **Mean Reversion** (dormante)
3. **Arbitrage Triangulaire** (dormante)
4. **Trend Following** (dormante)

### Fichiers à analyser
- /home/node/.openclaw/workspace/src/autobot/v2/strategies/grid_async.py
- /home/node/.openclaw/workspace/src/autobot/v2/strategies/mean_reversion.py
- /home/node/.openclaw/workspace/src/autobot/v2/strategies/triangular_arbitrage.py
- /home/node/.openclaw/workspace/src/autobot/v2/strategies/trend_async.py
- /home/node/.openclaw/workspace/src/autobot/v2/strategies/__init__.py

### Questions
1. Quelles sont les failles de sécurité potentielles dans ces stratégies?
2. Y a-t-il des race conditions ou deadlocks possibles?
3. Les stop-loss sont-ils robustes face à des gaps de prix?
4. Les stratégies dormantes peuvent-elles être activées par erreur?
5. Quelles améliorations recommandes-tu pour la production?

### Format de réponse
Réponds avec:
- 🔴 CRITIQUE (bloquant production)
- 🟡 WARNING (à corriger)
- 🟢 SUGGESTION (nice-to-have)
- Priorité numérotée de 1 à 10

NOMME TA SESSION: "REVIEW-OPUS-STRATEGIES"