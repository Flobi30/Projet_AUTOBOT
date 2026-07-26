# AUTOBOT — verrou d'exécution observation-only (2026-07-26)

Decision : `GO_RESEARCH_SHADOW_ONLY`.

Ce correctif ne constitue pas une autorisation de paper capital, de promotion
ou de live. Il élimine une ambiguïté héritée : le flag historique
`PAPER_TRADING=true` pouvait construire un portefeuille simulé et un exécuteur
paper alors que tous les garde-fous paper restaient désactivés.

## Périmètre

- Nouvelle sélection explicite du mode d'exécution dans
  `runtime_execution_mode.py`.
- Nouvel exécuteur `ObservationOnlyOrderExecutor` : aucune E/S réseau, aucun
  portefeuille, aucune base paper et toute mutation d'ordre est rejetée avec
  `observation_only_execution_disabled`.
- `main_async.py` n'instancie plus de client Kraken privé pour l'attestation
  dans ce mode ; l'attestation vérifie seulement la connectivité publique et
  les contrôles locaux.
- L'orchestrateur n'alloue aucun capital shadow/paper et expose un snapshot
  de capital explicitement nul, avec un budget d'observation séparé.
- `docker-compose.yml` force
  `AUTOBOT_OBSERVATION_ONLY_RUNTIME=true` en plus des garde-fous paper déjà
  forcés à `false`.

## Invariants vérifiés

| Invariant | Preuve |
| --- | --- |
| Le verrou observation-only prime | test de sélection de mode et invariant Compose |
| Un `false` explicite n'autorise rien | les trois gardes paper restent requises |
| Aucun ordre/fill/cancel possible | exécuteur non mutatif et tests de rejet |
| Aucune base `paper_trades.db` créée | test dans un répertoire temporaire vide |
| Aucun appel privé Kraken à l'attestation | test qui interdit auth, ordres et réconciliation privées |
| Les stratégies runtime restent observation-only | suite de non-régression runtime/shadow |
| Grid reste hors runtime officiel | invariants de déploiement existants rejoués |

## Validation locale

- `python -m compileall -q src` : PASS.
- Suite ciblée sécurité/parité/attestation : `58 passed`.
- Le benchmark micro-latence du hot path est désormais marqué `performance` :
  ce n'est pas un test fonctionnel fiable sur un hôte Windows partagé. Le
  seuil reste strict (`p99 < 10 us`) mais il doit être exécuté séparément sur
  un hôte inactif avec `python -m pytest -m performance -q`.
- Deux suites complètes précédentes avaient chacune `1884 passed, 6 skipped`
  et un seul échec de ce benchmark sous charge globale (`p99 17.6 us`, puis
  `12.0 us`). Le même test rejoué trois fois isolément a passé trois fois.
  Aucun code de stratégie ou de hot path n'a été modifié pour le masquer.
- `git diff --check` : PASS (avertissements CRLF Windows seulement).

Les benchmarks sont maintenant executes sur cinq batches rechauffes et
evalues par mediane P99, sans relever les seuils. Trois executions dediees
consecutives ont passe : `2 passed` a chaque run.

Validation finale fonctionnelle : `1883 passed, 6 skipped, 2 deselected`.
Les deux tests performance ont ensuite passe trois fois consecutivement dans
leur commande dediee.

## Déploiement attendu

Avant et après la mise à jour VPS, vérifier :

1. SHA GitHub, checkout VPS et image/conteneur identiques ;
2. `autobot-v2` et `/health` healthy, WebSocket connecté, 14 instances ;
3. les flags live/paper/promotion restent désactivés ;
4. les logs confirment `OBSERVATION-ONLY runtime` et ne montrent pas
   `PaperTradingExecutor initialised` ;
5. aucun ordre ni chemin d'ordre réel n'est observé.

## Risque résiduel et prochaine étape

La recherche ne dispose toujours pas de données historiques continues
matérielles ni d'un artefact stratégie `SHADOW_ELIGIBLE`. Les collecteurs et
diagnostics research peuvent continuer, mais aucune transition vers paper
capital ne peut être envisagée avant les gates de données, validation
statistique et revue humaine.
