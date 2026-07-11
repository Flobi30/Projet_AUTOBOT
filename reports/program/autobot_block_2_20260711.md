# AUTOBOT — Bloc 2 : registre d'expériences et validation statistique

## Décision

`GO` pour le Bloc 3, sous réserve du déploiement contrôlé et de la validation
VPS décrits dans ce rapport. Le bloc reste strictement **research-only** : il
ne crée aucun ordre, n'active pas le paper capital, ne modifie aucun sizing ou
levier et ne permet aucune promotion automatique.

## Livré

- Registre SQLite append-only des expériences, essais, transitions de gates,
  artefacts, réservations de holdout et imports de mémoire legacy.
- Fingerprint matériel déterministe : une expérience rejetée ou terminée ne
  peut pas être rouverte sous le même fingerprint.
- Pipeline canonique et monotone : `DATA_CHECK → NET_SMOKE → WALK_FORWARD →
  STRESS_MONTE_CARLO → SHADOW_REVIEW` ; les anciens libellés sont normalisés.
- Holdout immuable : sa réservation est tracée et toute optimisation qui
  l'utilise est refusée.
- Migration idempotente de la mémoire de recherche via
  `experiment-registry-migrate-memory` ; les observations historiques restent
  des archives et ne deviennent pas des preuves de promotion.
- Diagnostic statistique déterministe : PSR proxy par trade, DSR existant et
  intervalle bootstrap configurable avec seed et niveau de confiance tracés.
- Matrice des 24 couches mise à jour : experiment registry et multiple testing
  passent de `MISSING` à `PARTIAL` avec leurs preuves de test.

## Invariants vérifiés

- Les modules de recherche Bloc 2 n'importent aucun routeur d'ordres, client
  Kraken ou chemin runtime d'exécution.
- Les tables du registre refusent `UPDATE` et `DELETE` directement dans SQLite.
- Aucun essai ne peut être enregistré après rejet, données insuffisantes ou
  réussite complète de la revue shadow du même artefact matériel.
- Le résultat statistique est une aide à la recherche, jamais une permission de
  paper ou de live.

## Tests locaux

- `python -m compileall -q src` : succès.
- Suite ciblée Bloc 2 + CLI : `29 passed`.
- Suite complète `tests/research` : `297 passed`.
- Suite complète `tests/test_v2_cli.py` : `28 passed`.
- `git diff --check` : succès.

## Déploiement et migration vérifiés

Déployé au commit `aa8ddfed289709ff7dea043ac0a9706c008ded05` sur GitHub,
le VPS et le code reconstruit dans `autobot-v2`.

Commande exécutée une fois sur le conteneur :

```text
python -m autobot.v2.cli experiment-registry-migrate-memory \
  --memory-path data/research/alpha_research_memory.sqlite3 \
  --registry-path data/research/experiment_registry.sqlite3
```

Résultat : `12` archives legacy importées, de manière idempotente, dans
`data/research/experiment_registry.sqlite3`. Le fichier SQLite généré reste
hors Git conformément à `.gitignore`.

Le conteneur était healthy, le WebSocket connecté, 14 instances présentes et
les flags `LIVE_TRADING_CONFIRMATION`, router live et auto-promotion à `false`.
Aucun ordre live n'a été observé.

## Risques résiduels et suite

- Le registre capture les dimensions connues du runner ; les futures stratégies
  doivent fournir explicitement timeframe et régime lorsqu'elles les utilisent.
- PSR/DSR/bootstrap réduisent le risque de faux positif mais ne prouvent pas un
  alpha futur ; la validation hors échantillon et shadow restent obligatoires.
- Le Bloc 3 devra auditer puis unifier portefeuille, coûts, capacité et
  simulation sans activer paper capital.
