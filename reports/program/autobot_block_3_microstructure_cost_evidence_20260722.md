# AUTOBOT Bloc 3 — Microstructure Cost Evidence

## Décision

`GO` pour la frontière de coût research-only. La capacité d'exécution ne change
pas : aucune stratégie, promotion, capital paper, ordre réel ou flag runtime
n'est activé.

## Problème traité

Les profils canoniques de top-of-book étaient volontairement descriptifs. Une
recherche pouvait déjà référencer un fingerprint de modèle de coût, mais pas
prouver quelle observation microstructure avait justifié les hypothèses de
spread associées. Cette absence de liaison rendait la calibration moins
auditable.

## Implémentation

- Ajout de `MicrostructureCostEvidence`, une preuve immuable qui lie :
  - une identité exacte `kraken / spot / <symbol> / EUR` ;
  - le fingerprint de source du profil canonique ;
  - le spread research et le spread stress observés ;
  - les fingerprints des modèles de coût central et stress dérivés.
- L'évidence n'est créable que depuis un profil `RESEARCH_CALIBRATION_READY`.
- Le coût central prend `max(fallback_configuré, spread_research_observé)` et
  le coût stress prend `max(coût_central, spread_stress_observé)` : l'adaptateur
  ne peut jamais abaisser un coût.
- Les coûts dérivés sont marqués `runtime_comparable=false`; les captures REST
  publiques ne deviennent donc pas une preuve de parité runtime.
- Le gate `ScenarioEdgeReview` accepte cette évidence seulement si le signal,
  le marché et le fingerprint du coût central correspondent exactement. Toute
  absence ou incohérence est bloquante.
- Le pipeline shadow conserve le fingerprint de l'évidence dans son intention
  non exécutable quand le caller choisit explicitement de l'utiliser.

## Vérifications locales

- `py_compile` des modules et tests touchés : `PASS`.
- Smoke hermétique : profil prêt → coût central/stress conservateur → signal
  lié → `SCENARIO_EDGE_OK` : `PASS`.
- Le contrôle AST interdit tout import router, executor, paper trading ou
  signal handler dans le module d'évidence.
- La suite pytest ciblée reste à exécuter dans l'environnement de test rétabli
  avant le déploiement final; aucune conclusion de performance ne dépend de ce
  jalon.

## Invariants confirmés

- Research/shadow seulement.
- Aucun changement d'UI, sizing, leverage, paper capital ou live.
- Aucune mise à jour automatique d'un profil de coût global.
- Grid et aliases restent hors du chemin officiel.

## Risque résiduel

Les captures REST multi-session restent de la calibration batch. Une parité
runtime ne pourra être attestée qu'avec une source runtime point-in-time et une
comparaison contrôlée des mêmes observations.
