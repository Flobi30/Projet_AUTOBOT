# P18C Alpha Hypothesis Runner - 2026-07-09

## Verdict

PASS

AUTOBOT dispose maintenant d'un `Alpha Hypothesis Runner` research-only. Il lit `docs/research/alpha_hypotheses.json`, applique une politique d'autonomie par risque, avance automatiquement sur les gates research autorises et s'arrete avant toute etape qui augmenterait le risque.

## Architecture

Flux implemente :

```text
alpha_hypotheses.json
-> alpha_autonomy_policy.json
-> DATA_CHECK
-> FAST_NET_EDGE_TEST
-> WALK_FORWARD
-> STRESS_MONTE_CARLO
-> HUMAN_REVIEW boundary
-> reports only
```

Le runner n'importe pas et n'appelle pas de chemin d'ordre runtime. Il produit uniquement des rapports JSON/Markdown.

## Gates Implementes

- `DATA_CHECK` : AUTO_ALLOWED, neutral, stoppe en `DATA_MISSING`.
- `FAST_NET_EDGE_TEST` : AUTO_ALLOWED, neutral, utilise le smoke borne P18B.
- `WALK_FORWARD` : AUTO_ALLOWED, neutral, utilise l'adapter walk-forward seulement si demande et si le smoke passe.
- `STRESS_MONTE_CARLO` : AUTO_ALLOWED, neutral, reserve aux runs `full_research` apres walk-forward positif.
- `SHADOW_REVIEW_CANDIDATE` : HUMAN_REVIEW_REQUIRED, increase, aucune activation automatique.

## Premier Run Smoke

Commande executee sur VPS dans un container temporaire sans reseau :

```bash
python -m autobot.v2.cli alpha-hypothesis-runner \
  --hypothesis-id volatility_breakout \
  --mode smoke \
  --state-db /app/data/autobot_state.db \
  --data-paths /app/data/research/daily/ohlcv \
  --output-dir /app/reports/research/alpha_hypothesis_runner \
  --run-id p18c_alpha_hypothesis_runner_20260709 \
  --max-variants 5 \
  --max-symbols 6 \
  --max-runtime-seconds 120 \
  --commit cae5f8dcddcc36365167d28d0691452cc1bdc0a2
```

Resultat :

- Hypothese canonique : `volatility_breakout`
- Mode : `smoke`
- Gates executes : `DATA_CHECK`, `FAST_NET_EDGE_TEST`
- Final status : `KEEP_RESEARCH`
- Final decision : `NEXT_STAGE_AVAILABLE`
- Next allowed stage : `WALK_FORWARD`
- Runtime : 53.18 s
- Paper capital : false
- Live : false
- Promotable : false

Fast net-edge :

- Best variant : `fixed_tp_sl__min500bps__rr2__hold72h`
- Trades : 206
- PF net : 1.024769
- Net PnL : +10.992686 EUR
- Expectancy : +0.053363 EUR/trade
- Win rate : 36.89%
- Total costs : 20188 bps
- Main positive symbol : `BCHEUR`
- Weak/destructive symbols : `SOLEUR`, `XRPZEUR`

Interpretation : le smoke reste fragile. Le runner peut proposer `WALK_FORWARD`, mais ne lance pas cette etape en mode `smoke`.

## Hypotheses Lues

- `funding_basis`
- `liquidation_cascade`
- `volatility_breakout`
- `cross_momentum`
- `long_trend`

Aliases :

- `volatility_breakout_high_conviction` -> `volatility_breakout`

## Protections Anti-Loop

- `max_runtime_seconds`
- `max_variants`
- `max_symbols`
- `max_data_rows`
- stop automatique si data manquante
- stop automatique si edge net negatif
- aucune relance automatique d'une hypothese rejetee
- aucune selection paper/live par meilleur PnL historique

## Commandes Disponibles

```bash
python -m autobot.v2.cli alpha-hypothesis-runner --hypothesis-id volatility_breakout --mode data_check --data-paths data/research/daily/ohlcv
python -m autobot.v2.cli alpha-hypothesis-runner --hypothesis-id volatility_breakout --mode smoke --data-paths data/research/daily/ohlcv
python -m autobot.v2.cli alpha-hypothesis-runner --hypothesis-id volatility_breakout --mode walk_forward --data-paths data/research/daily/ohlcv
python -m autobot.v2.cli alpha-hypothesis-runner --hypothesis-id volatility_breakout --mode full_research --data-paths data/research/daily/ohlcv
```

## Securite

- `PAPER_TRADING=true`
- `LIVE_TRADING_CONFIRMATION=false`
- `STRATEGY_ROUTER_LIVE_ENABLED=false`
- `COLONY_AUTO_LIVE_PROMOTION=false`
- Aucun live
- Aucun paper capital
- Aucune promotion
- Aucun chemin d'ordre appele
- Aucun runtime trading touche
- Grid reste no-go

## Recommandation P18D

Utiliser le runner comme outil permanent. Prochaine action logique : lancer `alpha-hypothesis-runner --mode walk_forward` uniquement si l'on veut valider `volatility_breakout` plus strictement, en gardant l'activation shadow/paper hors automatisation.
