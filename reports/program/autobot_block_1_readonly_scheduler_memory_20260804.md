# Bloc 1 — mémoire SQLite en lecture seule pour le planificateur research

## Incident observé

Le cycle research-only `daily_2026_08_03T22_57_14Z` a bien publié sa
collecte, puis a échoué dans sa phase de planification isolée. Le planificateur
monte `data/research` en lecture seule, mais `ResearchMemoryStore` tentait
d'activer `PRAGMA journal_mode = WAL` même pour lire l'historique des essais.
SQLite a donc refusé l'ouverture de la base dans ce conteneur hermétique.

## Correction

- `ResearchMemoryStore(read_only=True)` ouvre la base via l'URI SQLite
  `mode=ro`, ne crée aucun schéma et ne change aucun mode de journalisation.
- Les lecteurs non mutables — planificateur d'hypothèses, scanner de capacité
  et contrôle d'éligibilité à un nouvel essai — utilisent ce mode explicite.
- Toute tentative d'append avec ce lecteur échoue explicitement.
- Le comportement append-only et WAL du propriétaire de la mémoire reste
  inchangé pour les processus qui écrivent réellement des résultats research.

## Sécurité et périmètre

- Correction limitée à la frontière des données de recherche.
- Le planificateur reste réseau désactivé, sans état runtime, sans secret et
  sans chemin d'ordre.
- Aucun paper capital, live, promotion, sizing ou levier n'est modifié.

## Tests locaux

- compilation Python des modules modifiés : `PASS`;
- tests ciblés scheduler/scanner/retry/service/CLI : `102 passed`;
- test spécifique : un lecteur `mode=ro` peut lire les événements existants,
  ne peut pas créer de table et refuse tout append;
- `git diff --check` : `PASS`.

## Validation VPS requise

Après déploiement, lancer uniquement le planificateur research dans le même
conteneur réseau désactivé et avec le même montage lecture seule. Son succès
confirme la correction. Ne pas relancer un batch de collecte, ne pas activer
une stratégie, et ne pas exécuter de NET_SMOKE, shadow, paper ou live dans le
cadre de cette correction.
