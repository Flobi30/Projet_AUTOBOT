# P18C Alpha Runner + Risk Mandate Non-Regression - 2026-07-09

## Verdict

PASS

P18C ajoute un runner alpha research-only, une politique d'autonomie par risque et une layer de mandats de risque. Aucun runtime trading n'a ete modifie.

## Commit

- GitHub/local/VPS : `cae5f8dcddcc36365167d28d0691452cc1bdc0a2`
- Main container : non redemarre
- Runner execute via container temporaire `--network none`

## Fichiers Modifies

- `docs/research/alpha_autonomy_policy.json`
- `docs/research/strategy_risk_mandates.json`
- `src/autobot/v2/cli.py`
- `src/autobot/v2/research/alpha_hypothesis_runner.py`
- `src/autobot/v2/research/strategy_risk_mandates.py`
- `tests/research/test_alpha_hypothesis_runner.py`
- `tests/research/test_strategy_risk_mandates.py`
- `reports/research/p18c_alpha_hypothesis_runner_2026-07-09.md`
- `reports/research/p18c_alpha_runner_risk_mandate_2026-07-09.md`
- `reports/non_regression/2026-07-09_p18c_alpha_runner_risk_mandate_non_regression.md`

## Tests

```powershell
python -m compileall -q src
$env:PYTHONPATH='src'; python -m pytest tests\research\test_alpha_hypothesis_runner.py tests\research\test_strategy_risk_mandates.py tests\research\test_alpha_smoke_runner.py tests\research\test_volatility_breakout_walk_forward.py tests\test_v2_cli.py -q
$env:PYTHONPATH='src'; python -m pytest tests\paper -q
$env:PYTHONPATH='src'; python -m pytest tests\research\test_archived_grid_defaults.py tests\test_strategy_validation_registry.py tests\test_v2_cli.py -q
```

Resultats :

- compileall : PASS
- targeted alpha/CLI tests : 49 passed
- paper tests : 72 passed
- grid/governance/CLI tests : 46 passed

## VPS

- repo HEAD : `cae5f8dcddcc36365167d28d0691452cc1bdc0a2`
- `autobot-v2` : healthy
- `/health` : healthy
- WebSocket : connected
- instances : 14
- `PAPER_TRADING=true`
- `LIVE_TRADING_CONFIRMATION=false`
- `STRATEGY_ROUTER_LIVE_ENABLED=false`
- `COLONY_AUTO_LIVE_PROMOTION=false`

## Trading Safety

- Aucun live active
- Aucun paper capital active
- Aucune promotion
- Aucun order path appele
- Aucun changement sizing/leverage
- Aucun changement UI
- Grid reste no-go

## Resultats P18C

Alpha runner smoke `volatility_breakout` :

- Final status : `KEEP_RESEARCH`
- Final decision : `NEXT_STAGE_AVAILABLE`
- Next stage : `WALK_FORWARD`
- PF net smoke : 1.024769
- Net PnL : +10.992686 EUR
- Aucun walk-forward lance en mode smoke
- Aucun shadow/paper/live active

Strategy autonomy check `volatility_breakout` :

- Mandat actif : true
- Mode : research
- Decision : `BLOCK`
- Raison : mandat no-capital/no-orders en P18C
- Human review required : false

## Risques Restants

- Le smoke `volatility_breakout` reste fragile et concentre le resultat sur quelques symboles.
- Les mandats ne sont pas encore branches au router/paper executor.
- Le runner ne doit pas etre confondu avec une autorisation paper/live.

## Action Recommandee

P18D doit utiliser le runner pour un `walk_forward` research-only ou enrichir les rapports de ranking hypotheses. Ne pas brancher paper/live tant qu'une revue humaine n'a pas valide un mandat capitalise.
