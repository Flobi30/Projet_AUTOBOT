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

## Variables runtime essentielles
Valeurs par défaut recommandées: orientées **paper + preflight** (donc pas d'ordres live par défaut).

| Variable | Obligatoire | Valeur défaut (`.env.example`) | Impact |
|---|---|---:|---|
| `PAPER_TRADING` | Oui | `true` | `true` = simulation, `false` active le mode live. |
| `DEPLOYMENT_STAGE` | Oui | `paper` | Gate de promotion (`paper`, `micro_live`, `small_live`). |
| `PREFLIGHT_ONLY` | Oui | `true` | `true` exécute uniquement les checks de démarrage. |
| `LIVE_TRADING_CONFIRMATION` | Oui | `false` | Doit rester `false` hors live; protection anti-ordre réel accidentel. |
| `DASHBOARD_API_TOKEN` | Oui | `change_me` | Authentification API dashboard (startup bloqué si absent). |
| `API_KEY_ASSIGNMENT_MODE` | Oui | `dedicated` | En live, impose une clé API dédiée par bot. |
| `ALLOW_SHARED_API_KEY` | Oui | `false` | Interdit le partage d'une clé API en live. |
| `UNIQUE_BOT_ID` | Oui | `bot-paper-01` | Identité du bot pour vérifier l'assignation de clé. |
| `API_KEY_ASSIGNED_BOT_ID` | Oui | `bot-paper-01` | Doit matcher `UNIQUE_BOT_ID` en live. |
| `MAX_LIVE_INSTANCES` | Oui | `1` | Limite stricte du nombre d'instances live simultanées. |
| `LEAKED_SSH_KEY_ROTATED_ACK` | Oui | `false` | Ack explicite après rotation d'un secret compromis. |
| `SECRET_EXPOSURE_MARKER_PATH` | Oui | `data/compromised_secret.marker` | Fichier marker: présent => startup bloqué. |
| `INITIAL_CAPITAL` | Oui | `1000.0` | Capital de base pour sizing et diagnostics. |
| `MAX_DRAWDOWN_PCT` | Oui | `10` | Seuil de drawdown global avant blocage/stop. |
| `RISK_PER_TRADE_PCT` | Oui | `1` | Risque maximum alloué par trade. |
| `MAX_POSITION_SIZE_PCT` | Oui | `20` | Taille max d'une position vs capital. |
| `KRAKEN_API_KEY` | Optionnelle* | vide | Nécessaire pour connexion exchange réelle. |
| `KRAKEN_API_SECRET` | Optionnelle* | vide | Nécessaire pour connexion exchange réelle. |

\* Optionnelles en préflight strict; recommandées pour valider la connectivité exchange.

## Paper-trading operations helpers
- Validate paper launch config: `python tools/paper_ops.py validate --env-file .env`
- Print start/run checklist: `python tools/paper_ops.py start-guide`
- Print paper feature-flag matrix: `python tools/paper_ops.py flags-guide`
- Generate post-run session summary: `python tools/paper_ops.py session-summary --log-file autobot_async.log --hours 24 --format markdown`

Detailed guide: `docs/PAPER_TRADING_OPERATIONS.md`.

## Mode live
Voir `docs/LIVE_PROMOTION_GATES.md`, `SECURITY.md`, `RUNBOOK.md`.

## Contribution policy
- Do not commit build outputs (`dashboard/dist/`) or dependencies (`dashboard/node_modules/`).
- Frontend artifacts must be generated during CI/CD builds (GitHub Actions/Netlify), not versioned in Git.
