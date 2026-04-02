## MISSION: Recherche d'Améliorations de Rendement — Approche SÉCURITÉ & ROBUSTESSE

Tu es Claude Opus 4.6, expert en trading algorithmique et sécurité financière.

### Contexte
AutoBot V2 est un robot de trading algorithmique crypto/forex avec :
- Stratégie Grid Trading (principale)
- Mean Reversion, Arbitrage Triangulaire, Trend Following (dormantes)
- 19 modules de performance (ATR, Kelly, Régime, Funding, etc.)
- Shadow trading avec validation PF > 1.5

### Objectif
Trouver des **pistes concrètes pour améliorer le Profit Factor (PF)** et le rendement global.

### Questions à explorer

1. **Quelles modifications de sécurité permettraient d'augmenter le PF ?**
   - Meilleurs stop-loss dynamiques
   - Protection contre le slippage
   - Gestion des gaps de marché

2. **Comment réduire les pertes tout en gardant les gains ?**
   - Filtres de marché plus stricts
   - Conditions d'entrée améliorées
   - Exit timing optimisé

3. **Quels sont les risques cachés qui réduisent le PF ?**
   - Corrélation entre instances
   - Surchauffe du marché
   - Manipulation de prix

4. **Stratégies de position sizing pour maximiser le rendement ?**
   - Kelly Criterion optimisations
   - Drawdown-based sizing
   - Volatilité-adaptive sizing

### Livrables
1. 5-10 idées concrètes numérotées par priorité (1-10)
2. Pour chaque idée: impact estimé sur PF, difficulté d'implémentation, risques
3. Focus sur le Grid Trading (stratégie principale)

Format: 🔴 HAUTE (impact PF > 0.3), 🟡 MOYENNE (impact 0.1-0.3), 🟢 FAIBLE (impact < 0.1)
