# AUTOBOT — Shadow artifact readiness snapshot audit — 2026-07-22

## Verdict

`GO` pour conserver un audit de gouvernance **research-only** sur snapshot
SQLite vérifié. `STOP` pour toute création d'artefact, démarrage shadow,
capital paper, promotion ou ordre : aucun candidat ne satisfait actuellement
les gates de recherche.

## Changement livré

- Commit de code déployé : `9eb7fa3863a480acaba2eda7553e693cf61a5644`.
- Nouvelle commande :
  `strategy-artifact-readiness-snapshot-audit`.
- Le diagnostic crée une copie temporaire par l'API SQLite backup avec une
  connexion source `mode=ro`, puis n'audite que cette copie.
- Une indisponibilité de snapshot renvoie `SNAPSHOT_UNAVAILABLE`; il n'existe
  aucun repli vers une lecture directe de la base runtime.
- Les connexions SQLite de l'audit sont désormais explicitement fermées. Cela
  évite les handles persistants qui empêchaient le nettoyage sur Windows.
- Un wrapper Docker/systemd est présent mais désactivé par défaut. Il monte
  uniquement `data/research` en lecture seule, sans réseau, secrets, état
  runtime ou surface d'exécution.

## Validation locale

- Tests ciblés readiness/CLI/résilience/déploiement : `66 passed`.
- Régression complète : `1879 passed, 6 skipped`.
- `python -m compileall -q src` : succès.
- `git diff --check` : succès.
- Contrôle de secrets sur le diff : succès.
- Le test WAL confirme que le snapshot lit les données validées, que la source
  reste inchangée sans écrivain concurrent et que les fichiers temporaires sont
  nettoyés.

## Smoke VPS isolé

- GitHub, checkout VPS et image `autobot-v2` :
  `9eb7fa3863a480acaba2eda7553e693cf61a5644`.
- Container : `healthy`; `/health` : orchestrateur `running`, WebSocket
  `connected`, `14` instances.
- Snapshot de `experiment_registry.sqlite3` : intégrité SQLite `ok`,
  aucune violation de clé étrangère, checksum source identique avant/après,
  snapshot supprimé après audit.
- Wrapper de snapshot : réseau désactivé, filesystem applicatif en lecture
  seule, capacités Linux retirées, `no-new-privileges`, seul `/tmp` éphémère
  est inscriptible.
- Timer systemd non installé/non activé; aucune exécution planifiée n'a été
  ajoutée.
- Flags conservés : live `false`, routeur live `false`, auto-promotion
  `false`, exécution paper `false`.
- Logs récents : aucune trace d'ordre live/soumis.

## État de la recherche observé

Le registre ne contient aucun artefact enregistré et aucun candidat shadow :

- `long_trend/regime_filtered_trend` : un essai incomplet et un essai
  `REJECTED` au net-smoke;
- `funding_basis/funding_extreme_reversion` : un essai
  `INSUFFICIENT_DATA` et un essai `REJECTED` au net-smoke.

Ces états sont des preuves de blocage, pas des autorisations de retester ou de
promouvoir. La suite reste la collecte et la validation research bornée, sans
capital paper ni live.

## Risque résiduel et prochaine action

Une base WAL qui ne peut pas être lue depuis le montage source en lecture seule
reste un blocage sain (`SNAPSHOT_UNAVAILABLE`), pas une raison de contourner
la frontière d'isolation. La prochaine étape utile est d'étendre la qualité
des données/features et la recherche bornée; toute stratégie déjà rejetée
reste fermée tant qu'elle ne dispose pas d'une nouvelle thèse ou d'un
changement matériel de données enregistré.
