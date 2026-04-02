## MISSION: Review Complète P0-P6 AutoBot V2 — Approche PERFORMANCE

Tu es expert en performance HFT.

### Contexte
Architecture asyncio visant <1µs latence, 2000+ instances.

### Fichiers à reviewer (même liste que REVIEW_P0P6_OPUS.md)
Focus sur:
1. Latence réelle du hot path (mesures vs objectifs)
2. Allocations mémoire dans les boucles critiques
3. Optimisations manquées (vectorisation, caching)
4. Scalabilité à 2000 instances
5. Contention sur ressources partagées
6. Efficacité du Ring Buffer vs alternatives

### Livrables
- Benchmarks critiques identifiés
- 🔴 Goulots d'étranglement bloquants
- 🟡 Optimisations recommandées
- 🟢 Micro-optimisations possibles
