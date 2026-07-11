# AUTOBOT — Bloc 6 : résilience et revue paper humaine

## Décision finale du programme

`NOT_READY_FOR_HUMAN_PAPER_REVIEW`.

Ce résultat est volontairement sûr : le programme n'active aucun capital
paper, aucun live et aucun mandat. Les couches runtime identifiées `UNSAFE` ou
`PARTIAL` empêchent de produire un dossier prêt pour décision humaine.

## Livré

- Matrice fail-closed couvrant WebSocket, API, données périmées, SQLite
  verrouillée, disque plein, redémarrage et ordre incertain.
- Retry/backoff borné : un échec final reste visible, jamais masqué.
- Copie SQLite avec `PRAGMA integrity_check`, hash source/backup et refus de
  prétendre chiffrer une sauvegarde locale sans couche approuvée.
- Génération d'un dossier non-autorisant à partir de la matrice des 24 couches.
  Seul un ensemble de preuves `VERIFIED`, avec kill switch, réconciliation et
  restauration testés, peut porter le libellé `READY_FOR_HUMAN_PAPER_REVIEW`.
- Runbook fail-closed/réconciliation/restauration/secrets versionné.

## Bloqueurs actuels

- Portefeuille runtime, paper historique et OMS runtime ne sont pas encore
  vérifiés : ils ont des bypass ou lacunes de cycle de vie.
- Les tests de kill switch, réconciliation exchange réelle et restauration sur
  le VPS ne sont pas des preuves de production.
- Les règles Kraken par paire et la parité complète paper/live restent à
  intégrer avant qu'un mandat humain puisse même être envisagé.

## Garantie de périmètre

- Aucun live, paper capital, promotion automatique, sizing ou levier n'a été
  activé ou modifié par ce bloc.
- Le résultat utile du programme est donc un système plus fiable qui sait dire
  « non prêt » plutôt que de forcer un ordre ou une promesse de rentabilité.
