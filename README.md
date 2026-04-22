# Projet_AUTOBOT

Entrypoint officiel: `src/autobot/v2/main_async.py`.

`src/autobot/v2/main.py` est conservé uniquement comme wrapper de compatibilité vers `main_async.py`.

## Quick start
1. Copier `.env.example` vers `.env`.
2. Remplir les variables obligatoires (token dashboard, limites de risque, etc.).
3. Lancer un préflight sans trading:
   ```bash
   PREFLIGHT_ONLY=true python -u src/autobot/v2/main_async.py
   ```
4. Lancer en paper:
   ```bash
   PAPER_TRADING=true DEPLOYMENT_STAGE=paper python -u src/autobot/v2/main_async.py
   ```

## Paper-trading operations helpers
- Validate paper launch config: `python tools/paper_ops.py validate --env-file .env`
- Print start/run checklist: `python tools/paper_ops.py start-guide`
- Print paper feature-flag matrix: `python tools/paper_ops.py flags-guide`
- Generate post-run session summary: `python tools/paper_ops.py session-summary --log-file autobot_async.log --hours 24 --format markdown`

Detailed guide: `docs/PAPER_TRADING_OPERATIONS.md`.

## Mode live
Voir `docs/LIVE_PROMOTION_GATES.md`, `SECURITY.md`, `RUNBOOK.md`.


## Contribution
Voir `CONTRIBUTING.md`.

Règle frontend impérative: tout code React/TSX doit vivre sous `dashboard/src`.
