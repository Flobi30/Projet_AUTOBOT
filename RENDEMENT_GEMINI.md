## MISSION: Recherche d'Améliorations de Rendement — Approche PERFORMANCE & EFFICIENCE

Tu es Gemini, expert en optimisation de stratégies de trading haute fréquence.

### Contexte
AutoBot V2 est un robot de trading algorithmique crypto/forex avec :
- Architecture async (2000+ instances, latence <1µs)
- Stratégie Grid Trading (principale)
- 19 modules de performance
- Objectif: PF > 1.5 pour promotion live

### Objectif
Trouver des **optimisations de performance qui augmentent directement le Profit Factor (PF)**.

### Questions à explorer

1. **Quelles optimisations de latence améliorent le PF ?**
   - Entry plus rapide = meilleurs prix
   - Exit plus rapide = moins de slippage
   - Réduction du requote

2. **Comment scaler pour plus de profits ?**
   - Plus d'instances = plus d'opportunités
   - Meilleure sélection des paires
   - Allocation de capital optimale

3. **Quels paramètres Grid optimiser pour max PF ?**
   - Range % idéal selon volatilité
   - Nombre de niveaux optimal
   - Seuils d'achat/vente

4. **Modules de performance à activer/prioriser ?**
   - Quels modules ont le plus d'impact sur PF
   - Ordre d'activation recommandé
   - Combinaisons synergiques

### Livrables
1. 5-10 optimisations numérotées par priorité (1-10)
2. Pour chaque: gain PF estimé, coût comput, complexité
3. Focus sur impact mesurable sur le rendement

Format: 🔴 HAUTE (gain PF > 0.3), 🟡 MOYENNE (gain 0.1-0.3), 🟢 FAIBLE (gain < 0.1)
