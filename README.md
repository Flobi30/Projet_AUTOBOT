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
- Generate pair attribution report: `python tools/paper_ops.py pair-attribution --db-path data/autobot_state.db --format markdown`
- Generate rejected-opportunity analytics: `python tools/paper_ops.py rejected-opportunities --journal-path data/decision_journal.jsonl --format markdown`
- Generate consolidated profitability review: `python tools/paper_ops.py profitability-review --db-path data/autobot_state.db --journal-path data/decision_journal.jsonl --format markdown`
- Generate autonomous recommendation-first review: `python tools/paper_ops.py autonomous-review --db-path data/autobot_state.db --journal-path data/decision_journal.jsonl --format markdown`

Detailed guide: `docs/PAPER_TRADING_OPERATIONS.md`.

## Decision Journal (Lot 1)
- Feature-flagged structured decision logging (append-only JSONL) for major runtime decisions.
- Default safe/off: `ENABLE_DECISION_JOURNAL=false`.
- Path/config: `DECISION_JOURNAL_PATH`, `DECISION_JOURNAL_FLUSH_EVERY`, `DECISION_JOURNAL_MAX_SYMBOLS`.

## Mode live
Voir `docs/LIVE_PROMOTION_GATES.md`, `SECURITY.md`, `RUNBOOK.md`.
