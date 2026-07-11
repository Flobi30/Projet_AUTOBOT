# AUTOBOT — Bloc 5 : OMS, ledger, réconciliation et TCA hermétiques

## Décision

`GO` pour le modèle hermétique de recherche/shadow. `REWORK` reste obligatoire
avant toute revue paper humaine, car le handler runtime historique contourne
encore le chemin OMS central et le moteur paper historique n'a pas un cycle de
fills/stops suffisamment fidèle.

## Livré

- OMS shadow append-only : intention, transitions autorisées, événements
  inconnus, partial fills, annulation et états terminaux.
- Protection déterministe contre les doublons de client order ID, événement et
  fill ; la réexécution d'un fill identique ne crée pas de position double.
- Ledger shadow append-only, reconstruction de positions après redémarrage et
  refus d'un sell fill supérieur à la position reconstruite.
- Réconciliation indépendante : toute divergence de positions ou d'ordres
  ouverts produit `RECONCILIATION_REQUIRED` et `trading_halted=true`.
- TCA hermétique : prix signal/décision/arrivée/fill, frais, spread, slippage,
  latence, funding et implementation shortfall.

## Invariants

- Seules les intentions `shadow` sont acceptées.
- Aucun router, handler runtime ou moteur paper n'est importé.
- Les tables SQLite refusent `UPDATE` et `DELETE`.
- Le paper/live restent explicitement interdits dans tous les objets créés.

## Risques résiduels

- Ce modèle n'est pas encore le chemin runtime : les bypass du handler et les
  contraintes Kraken par paire restent bloquants avant paper.
- La réconciliation avec une réponse exchange réelle sera traitée uniquement
  après une validation humaine distincte ; aucun endpoint privé n'est utilisé.
