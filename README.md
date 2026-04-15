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

## Mode live
Voir `docs/LIVE_PROMOTION_GATES.md`, `SECURITY.md`, `RUNBOOK.md`.
