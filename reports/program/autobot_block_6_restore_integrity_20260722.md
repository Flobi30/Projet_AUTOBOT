# AUTOBOT — Bloc 6 : intégrité de restauration SQLite

## Décision

`GO` pour ce sous-ensemble de résilience. Cette modification ne rend pas
AUTOBOT éligible au paper : elle renforce seulement la preuve qu'une base
SQLite peut être sauvegardée et restaurée sans utiliser le chemin d'ordres.

## Correction

- Une sauvegarde est construite dans un fichier temporaire privé puis publiée
  sans écraser une destination existante ; un échec ne laisse plus de snapshot
  partiel à confondre avec une sauvegarde valide.
- La sauvegarde et le restore drill exécutent maintenant `PRAGMA integrity_check`
  et `PRAGMA foreign_key_check`.
- Toute violation référentielle bloque le résultat et aucun manifest ne peut
  déclarer une sauvegarde valide dans ce cas.

## Preuve VPS

Le 2026-07-22, un restore drill éphémère a été exécuté contre la base runtime
montée en lecture seule dans un conteneur isolé : réseau coupé, root filesystem
en lecture seule, privilèges supprimés et stockage temporaire en mémoire.

- intégrité SQLite : OK ;
- cohérence schéma et nombre de lignes : OK ;
- sauvegarde temporaire supprimée : OK ;
- aucun fichier runtime, ordre, capital paper, promotion ou flag live modifié.

## Validation locale

```text
python -m compileall -q src
pytest tests/research/test_resilience_readiness.py \
       tests/research/test_runtime_resilience_audit.py \
       tests/research/test_sqlite_backup_deployment.py \
       tests/research/test_runtime_resilience_deployment.py \
       tests/test_v2_cli.py -q
```

Résultat : `60 passed`.

Les tests couvrent aussi un fichier SQLite physiquement valide mais contenant
une clé étrangère invalide : backup et restore drill le rejettent, sans modifier
la source ni conserver un fichier de destination.

## Limites restantes

- La sauvegarde persistante automatisée reste désactivée tant qu'une politique
  de rétention et de chiffrement hors VPS n'est pas formellement définie.
- Le système reste en research/shadow ; aucune des gates paper/live n'est
  ouverte par ce travail.
