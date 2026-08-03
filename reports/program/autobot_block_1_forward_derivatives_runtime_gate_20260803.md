# AUTOBOT Bloc 1 — gate runtime des dérivés forward (2026-08-03)

## Décision

`WAITING_FOR_MORE_DATA`.

Le collecteur public Kraken Futures, les snapshots de features et la parité
point-in-time fonctionnent en mode research-only. Cela ne rend pas encore
`funding_basis` ni aucune autre stratégie éligible au shadow, au paper ou au
live.

## Preuves runtime

- Les timers `funding`, `open-interest`, `future-basis` et
  `feature-snapshot` sont `enabled` et `active` sur le VPS.
- Le dernier job funding observé s'est terminé avec `Result=success` et
  `ExecMainStatus=0`; il utilise uniquement l'endpoint public d'historique de
  funding Kraken Futures.
- Le manifest forward le plus récent inspecté est
  `derivatives_forward_features_2026_08_03T16_18_55Z_derivatives_feature_snapshot.json`.
  Il est `READY`, `forward_capture_only`, `parity_ok=true` et
  `runtime_parity_proven=true`.
- Son bundle contient les features `funding_rate_relative`, `basis_bps` et
  `open_interest_change_24_pct`; le basis reste explicitement same-quote et
  interdit toute conversion implicite USD/EUR.
- Les mappings explicites incluent `PF_XBTUSD -> BTCZEUR` et
  `PF_ETHUSD -> ETHZEUR`. Le perpétuel reste une feature directionnelle : les
  retours et coûts restent calculés sur le marché spot EUR.

## Seuil encore non atteint

Le collecteur a enregistré 24 observations funding
`AVAILABLE_AFTER_FORWARD_CAPTURE` pour chacun de `PF_XBTUSD` et `PF_ETHUSD`.
L'adaptateur `funding_basis` impose au minimum 30 observations funding et 30
barres spot/dérivés éligibles par symbole. Les six observations manquantes
empêchent donc volontairement toute évaluation officielle à ce stade.

Le prochain snapshot de features programmé doit réévaluer ce seuil avec les
captures forward supplémentaires. Il ne doit déclencher ni `NET_SMOKE`, ni
shadow, ni paper automatiquement.

## Validation locale

```text
python -m pytest \
  tests/research/test_kraken_futures_derivatives_collector.py \
  tests/research/test_derivatives_feature_snapshot.py \
  tests/research/test_derivatives_feature_snapshot_deployment.py \
  tests/research/test_derivatives_spot_context.py \
  tests/research/test_funding_basis_research_adapter.py -q
```

Résultat : `60 passed`.

## Invariants conservés

- `PAPER_TRADING=false`;
- `LIVE_TRADING_CONFIRMATION=false`;
- `STRATEGY_ROUTER_LIVE_ENABLED=false`;
- `COLONY_AUTO_LIVE_PROMOTION=false`;
- aucune clé privée, endpoint d'ordre, mandat, sizing ou leverage impliqué;
- grid et aliases restent retirés du runtime.

## Prochaine action autorisée

Après que le prochain manifest forward aura prouvé le seuil minimal, effectuer
uniquement un `DATA_CHECK` humainement guidé. Une nouvelle hypothèse ne pourra
avancer que si ce check et les gates statistiques existants le permettent.
