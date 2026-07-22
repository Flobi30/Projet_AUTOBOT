# AUTOBOT — Bloc 3 : provenance des snapshots shadow

## Décision

**GO — research/shadow uniquement.** Cette tranche ne crée aucun `ExecutionCommand`, ne modifie aucun routeur, et n'autorise ni capital paper, ni promotion, ni live.

Implémentation initiale : `93ef061502249621173c22158819ba17b9e85903`.
Raffinement top-of-book : `e11364613c82e814e817f30a4797cdaa42f16493`.

## Problème traité

Le simulateur shadow acceptait auparavant un prix accompagné d'un seul timestamp. Cela ne permettait pas de prouver que le prix appartenait au même marché que l'intention, ni qu'AUTOBOT pouvait effectivement le connaître au moment du fill.

## Contrat ajouté

`ShadowMarketSnapshot` exige maintenant :

- `MarketIdentity` exact ;
- `event_time`, `available_time`, `ingestion_time` UTC et ordonnés ;
- `source_snapshot_id` ;
- empreinte SHA-256 de la source ;
- prix, bid/ask et liquidité observés.

Le simulateur choisit les snapshots selon `max(available_time, ingestion_time)`, refuse une identité de marché différente, et expire une donnée arrivée trop tard. Lorsqu'un bid/ask atomique est présent, il utilise le milieu du carnet comme référence avant de charger le demi-spread, le slippage et la latence ; un dernier prix potentiellement périmé ne peut donc pas améliorer un fill. Le fill shadow conserve cette provenance. Son idempotence inclut l'empreinte de toute la séquence de snapshots : une reprise avec une donnée différente est donc rejetée au lieu de réutiliser silencieusement un ancien résultat.

Les `MarketExecutionRules` sont également liés à une `MarketIdentity` explicite et à un snapshot public Kraken fingerprinté ; leur mapping est lui-même indexé par `MarketIdentity`. Un symbole seul ne suffit plus.

## Preuves de test

- `py_compile` des modules touchés : PASS.
- `tests/research/test_execution_simulator.py`
- `tests/research/test_contract_shadow_pipeline.py`
- `tests/research/test_microstructure_cost_evidence.py`
- `tests/research/test_canonical_microstructure_profile.py`

Résultat local : **51 passed**.

Validation VPS hermétique, depuis une image Docker lecture seule et sans réseau : **51 passed**, avec un seul avertissement attendu d'écriture du cache pytest dans le montage lecture seule.

Le déploiement VPS a confirmé :

- dépôt, label de l'image et conteneur sur `e11364613c82e814e817f30a4797cdaa42f16493` ;
- hash identique de `execution_simulator.py` sur disque et dans `/app` ;
- `/health` healthy, orchestrateur en cours, WebSocket connecté, 14 instances ;
- quatre timers research restaurés et actifs ;
- `LIVE_TRADING_CONFIRMATION=false`, `STRATEGY_ROUTER_LIVE_ENABLED=false`, `COLONY_AUTO_LIVE_PROMOTION=false`, `ENABLE_INSTANCE_SPLIT_EXECUTOR=false` ;
- aucune ligne `Traceback`, `CRITICAL`, `ERROR` ou ordre live dans les 15 minutes de logs examinées.

## Invariants vérifiés

- une donnée `BTCUSD` ne peut pas remplir une intention `BTCEUR` ;
- une ingestion tardive ne peut pas produire un fill ;
- une reprise avec un autre snapshot est une collision d'idempotence ;
- la provenance complète est jointe au fill non exécutable ;
- les imports research restent isolés du routeur, du handler et du paper engine.

## Limites et suite

Le statut de la couche reste `PARTIAL`. Ce contrat rend la simulation honnête, mais il ne prouve pas encore la parité avec un flux runtime. Les données microstructure batch demeurent explicitement non comparables au runtime ; aucune promotion ne peut s'appuyer dessus seule.
