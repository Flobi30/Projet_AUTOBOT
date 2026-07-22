# AUTOBOT — Bloc 3 : parité coût validé / coût simulé

## Décision

**GO — research/shadow uniquement.** Aucune commande exécutable, aucun capital paper, aucune promotion et aucun flag live ne sont créés ou modifiés.

Implémentation : `87d9fb02cbee817730dba0950ee0a2c79407b1c9`.

## Risque éliminé

Une hypothèse pouvait être validée avec un `ExecutionCostConfig` et atteindre le simulateur avec une autre configuration de frais, spread, slippage ou latence. Ce décalage pouvait rendre un résultat shadow plus favorable ou simplement non reproductible.

## Contrôle ajouté

Le pipeline contractuel :

1. valide l'edge avec le coût central immuable ;
2. dérive le coût requis pour le scénario réellement simulé (`central`, `pessimistic` ou `stress`) ;
3. compare son fingerprint au profil appliqué par le simulateur ;
4. bloque la simulation avec `simulation_cost_model_fingerprint_mismatch` en cas d'écart.

Le `OrderIntent` non exécutable et le `FillResult` shadow enregistrent l'empreinte du coût de simulation et le nom du scénario. Une dérivation pessimiste exacte est permise ; une baisse ou une substitution silencieuse ne l'est pas.

## Preuve locale

Les tests research, portefeuille et contrats ciblés passent : **53 passed** localement et dans une image Docker VPS lecture seule, sans réseau. Le seul avertissement VPS attendu concerne le cache pytest non inscriptible dans le montage lecture seule.

Ils couvrent notamment :

- rejet d'un simulateur dont le slippage diffère du coût validé ;
- acceptation d'une dérivation pessimiste exacte ;
- présence de l'empreinte et du scénario appliqués dans l'intention et le fill shadow ;
- absence d'import du routeur, du handler ou du paper engine.

VPS après déploiement : dépôt et image Docker alignés sur le commit d'implémentation, `/health` healthy, WebSocket connecté, 14 instances et quatre timers research actifs. Les flags `LIVE_TRADING_CONFIRMATION`, `STRATEGY_ROUTER_LIVE_ENABLED`, `COLONY_AUTO_LIVE_PROMOTION` et `ENABLE_INSTANCE_SPLIT_EXECUTOR` restent tous à `false`.

## Limite

Le statut du Bloc 3 demeure `PARTIAL`. Cette protection assure la parité interne research/shadow, mais ne transforme pas les données batch microstructure en preuve de parité runtime ni en autorisation paper/live.
