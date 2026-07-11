# AUTOBOT Block 0.1 — Stabilisation de la fondation

**Décision : GO.**  Ce bloc ne modifie aucun flag de trading, sizing, levier,
promotion, capital paper ou chemin d'ordre runtime.

## Changements validés

- Le test runner charge `src/` explicitement et ne collecte plus les scripts de
  benchmark comme des tests.
- L'initialisation du logger et du kill switch est différée au démarrage du
  runtime : importer ou construire les composants de test n'écrit plus dans le
  worktree.
- Le lock de test inclut désormais PyYAML et reste compatible Python 3.11.
- Les contrats v1 distinguent `OrderIntent` (non exécutable), `RiskDecision` et
  `ExecutionCommand`; ils disposent de sérialisation déterministe et
  fingerprint.
- La mémoire de recherche par défaut est append-only dans
  `data/research/alpha_research_memory.sqlite3`; l'ancien JSON est lu une fois
  et migré de façon idempotente, et un export compact de revue est disponible.
- La matrice versionnée des 24 couches lie statut, propriétaire, contrat,
  preuve et test associé.
- Les documents historiques les plus susceptibles de réintroduire Grid ou une
  exécution spéculative sont explicitement non normatifs.

## Preuves de test

- Collection hermétique : `1444` tests collectés sans erreur.
- Suite unitaire hermétique : `1167 passed`, `277 deselected`.
- Suite d'intégration hermétique : `280 passed`, `1165 deselected`.
- Les quatre avertissements restants sont des marques `asyncio` inutiles dans
  des tests historiques du routeur; ils ne changent pas le comportement
  runtime et seront traités dans la vague OMS.
- `python -m compileall -q src` et `git diff --check` passent dans le worktree
  d'intégration.

## Risques résiduels et transition

- `reports/research/alpha_research_memory.json` est conservé temporairement
  comme seed de migration afin de préserver les données runtime existantes. Le
  runtime n'y écrit plus par défaut. Sa sortie complète de Git sera faite après
  migration vérifiée du checkout actif, sans effacer une donnée locale.
- La suite de tests intègre encore des composants Grid archivés; cela ne les
  rend pas routables. La politique runtime continue de les bloquer.
- Le Bloc 1 peut commencer : temporalité point-in-time, canonical data et
  feature registry. Les stratégies restent research/shadow-only.
