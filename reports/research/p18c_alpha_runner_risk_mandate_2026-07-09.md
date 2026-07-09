# P18C Strategy Risk Mandate Layer - 2026-07-09

## Verdict

PASS

La `Strategy Risk Mandate Layer` existe maintenant en research-only. Elle definit l'enveloppe de risque dans laquelle une strategie pourra plus tard fonctionner sans validation humaine par trade. En P18C, elle n'est pas branchee au paper executor ni au runtime order path.

## Politique Centrale

AUTOBOT peut reduire le risque automatiquement :

- reject
- stop
- downgrade
- kill
- block
- report

AUTOBOT ne peut jamais augmenter le risque automatiquement :

- paper capital
- hausse capital
- hausse position
- ajout symbole
- desactivation kill rules
- sizing/leverage
- live
- reactivation apres kill capital

## Fichiers

- `docs/research/strategy_risk_mandates.json`
- `docs/research/alpha_autonomy_policy.json`
- `src/autobot/v2/research/strategy_risk_mandates.py`

## Mandats Initiaux

- `volatility_breakout` : research-only, capital 0 EUR, no paper/live.
- `trend_momentum` : benchmark/no-capital.
- `mean_reversion` : benchmark/no-capital.
- `high_conviction_swing` : research-only/no-capital.

Tous les mandats imposent :

- `human_approved_required_for_risk_increase=true`
- `paper_capital_allowed=false`
- `live_allowed=false`

## CLI Read-Only

Commande executee sur VPS :

```bash
python -m autobot.v2.cli strategy-autonomy-check \
  --strategy-id volatility_breakout \
  --state-db /app/data/autobot_state.db \
  --mandates /app/docs/research/strategy_risk_mandates.json
```

Resultat :

- Mandat actif : true
- Mode autorise : `research`
- Decision actuelle : `BLOCK`
- Human review required : false
- Risk direction : reduce
- Paper capital : false
- Live : false
- Promotable : false

Raisons du blocage :

- `order_type_allowed`
- `trades_per_day_within_limit`
- `orders_per_minute_within_limit`
- `edge_to_cost_ratio`

Ce blocage est attendu : le mandat P18C est volontairement no-capital/no-orders.

## Comportement PreTradeAutonomyGate

Checks modelises :

- strategie autorisee
- symbole autorise
- timeframe autorise
- type d'ordre autorise
- notional, exposition symbole, exposition totale
- daily loss
- drawdown
- trades par jour
- orders par minute
- frais journaliers
- slippage
- spread
- data freshness
- edge/cost ratio
- kill switch

Un seul hard check en echec retourne `BLOCK`.

## AutoKill / Downgrade

Le moteur side-effect free retourne `KILL` si :

- rolling PF < seuil
- rolling expectancy < seuil
- pertes consecutives >= cooldown
- erreurs ledger
- divergence paper/backtest trop forte
- strategie deja killed

Il ne reactive jamais automatiquement une strategie en mode capital.

## Securite

- Non branche au paper executor
- Non branche au live
- Non branche au router runtime
- Aucun ordre
- Aucun sizing/leverage
- Aucun changement UI
- Grid rejete par policy runtime

## Recommandation P18D

Conserver la layer en read-only. La prochaine etape utile serait de brancher ses decisions uniquement dans les rapports research, puis seulement plus tard dans un dry-run de router, sans capital.
