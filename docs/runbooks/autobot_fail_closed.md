# AUTOBOT — Runbook fail-closed

## État incertain

Ne pas augmenter le risque. Conserver les flags paper/live inchangés, relever
le commit et l'état de santé, puis appliquer l'action déterminée par le module
de résilience : blocage des signaux, blocage des ordres, annulation, réduction
ou arrêt.

## Divergence ordre ou position

1. Arrêter les nouvelles entrées.
2. Préserver le ledger et les logs ; ne pas supprimer de fichier runtime.
3. Exécuter la réconciliation indépendante.
4. Garder l'état `RECONCILIATION_REQUIRED` tant que la divergence n'est pas
   expliquée par une source vérifiable.

## Restauration

1. Travailler sur une copie SQLite vérifiée par `PRAGMA integrity_check`.
2. Vérifier le hash de la source et de la sauvegarde.
3. Restaurer dans un emplacement de validation isolé.
4. Ne reprendre aucune entrée tant que santé, ledger et réconciliation ne sont
   pas cohérents.

## Secrets

Ne pas copier, afficher, commiter ni intégrer de clé SSH/API dans un rapport.
Les sauvegardes chiffrées nécessitent une couche approuvée et séparée ; le
module de résilience refuse de prétendre chiffrer un backup local.
