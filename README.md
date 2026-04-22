# Projet_AUTOBOT

Entrypoint officiel: `src/autobot/v2/main_async.py`.

`src/autobot/v2/main.py` est conservé uniquement comme wrapper de compatibilité vers `main_async.py`.

## Quick start
1. Copier `.env.example` vers `.env`.
2. Remplir les variables obligatoires (cf. matrice ci-dessous selon le mode).
3. Lancer un préflight d'attestation (sans trading):
   ```bash
   PREFLIGHT_ONLY=true PAPER_TRADING=false DEPLOYMENT_STAGE=paper \
   KRAKEN_API_KEY=krk_xxx KRAKEN_API_SECRET=krk_yyy \
   python -u src/autobot/v2/main_async.py
   ```
4. Lancer en paper réel (attestation OK + trading paper activé):
   ```bash
   PREFLIGHT_ONLY=false PAPER_TRADING=true DEPLOYMENT_STAGE=paper \
   KRAKEN_API_KEY=krk_xxx KRAKEN_API_SECRET=krk_yyy \
   python -u src/autobot/v2/main_async.py
   ```

## Variables runtime essentielles
Valeurs par défaut recommandées: orientées **paper + preflight** (donc pas d'ordres live par défaut).

### Règle explicite sur les credentials exchange
- **Préflight complet ou paper réel**: `KRAKEN_API_KEY` et `KRAKEN_API_SECRET` sont **obligatoires** (la connectivité exchange est vérifiée).
- **Modes purement offline/mock**: laissez les credentials vides **et activez explicitement** `MOCK_BROKER=true` (ou votre backend mock équivalent) pour bypasser toute dépendance exchange.

### Matrice “mode d’exécution → variables obligatoires”

| Mode d'exécution | Variables obligatoires | Notes |
|---|---|---|
| Préflight complet (connectivité réelle) | `PREFLIGHT_ONLY=true`, `DEPLOYMENT_STAGE=paper`, `PAPER_TRADING=false`, `DASHBOARD_API_TOKEN`, `INITIAL_CAPITAL`, `MAX_DRAWDOWN_PCT`, `RISK_PER_TRADE_PCT`, `MAX_POSITION_SIZE_PCT`, `KRAKEN_API_KEY`, `KRAKEN_API_SECRET` | Attestation full-stack sans prise de position. |
| Paper réel (trading simulé connecté exchange) | `PREFLIGHT_ONLY=false`, `DEPLOYMENT_STAGE=paper`, `PAPER_TRADING=true`, `LIVE_TRADING_CONFIRMATION=false`, `DASHBOARD_API_TOKEN`, `INITIAL_CAPITAL`, `MAX_DRAWDOWN_PCT`, `RISK_PER_TRADE_PCT`, `MAX_POSITION_SIZE_PCT`, `KRAKEN_API_KEY`, `KRAKEN_API_SECRET` | Mode paper opérationnel après attestation. |
| Offline/mock pur | `PREFLIGHT_ONLY=true`, `PAPER_TRADING=true`, `DEPLOYMENT_STAGE=paper`, `MOCK_BROKER=true`, `DASHBOARD_API_TOKEN`, `INITIAL_CAPITAL`, `MAX_DRAWDOWN_PCT`, `RISK_PER_TRADE_PCT`, `MAX_POSITION_SIZE_PCT` | Aucun appel exchange; credentials Kraken non requis. |

### Exemple de lancement paper “attestation pass + trading paper activé”

```bash
# 1) Attestation (doit passer)
PREFLIGHT_ONLY=true PAPER_TRADING=false DEPLOYMENT_STAGE=paper \
DASHBOARD_API_TOKEN=change_me INITIAL_CAPITAL=1000 \
MAX_DRAWDOWN_PCT=10 RISK_PER_TRADE_PCT=1 MAX_POSITION_SIZE_PCT=20 \
KRAKEN_API_KEY=krk_xxx KRAKEN_API_SECRET=krk_yyy \
python -u src/autobot/v2/main_async.py

# 2) Trading paper activé (mêmes minima)
PREFLIGHT_ONLY=false PAPER_TRADING=true DEPLOYMENT_STAGE=paper \
LIVE_TRADING_CONFIRMATION=false DASHBOARD_API_TOKEN=change_me \
INITIAL_CAPITAL=1000 MAX_DRAWDOWN_PCT=10 RISK_PER_TRADE_PCT=1 MAX_POSITION_SIZE_PCT=20 \
KRAKEN_API_KEY=krk_xxx KRAKEN_API_SECRET=krk_yyy \
python -u src/autobot/v2/main_async.py
```

### Point de sécurité critique: `LEAKED_SSH_KEY_ROTATED_ACK`
- Cette variable doit rester à `false` tant que la rotation des secrets compromis n'a **pas** été exécutée et vérifiée en conditions opérationnelles.
- Ne la positionner à `true` qu'après validation explicite (rotation effective + confirmation que les anciens secrets sont invalides).

## Configuration minimale paper qui passe l’attestation

Exemple minimal avec les **valeurs exactes attendues** pour passer l'attestation sécurité en mode paper:

```dotenv
APP_ENV=production
DEPLOYMENT_STAGE=paper
PAPER_TRADING=true
PREFLIGHT_ONLY=true
LIVE_TRADING_CONFIRMATION=false

DASHBOARD_API_TOKEN=change_me
API_KEY_ASSIGNMENT_MODE=dedicated
ALLOW_SHARED_API_KEY=false
UNIQUE_BOT_ID=bot-paper-01
API_KEY_ASSIGNED_BOT_ID=bot-paper-01
MAX_LIVE_INSTANCES=1

LEAKED_SSH_KEY_ROTATED_ACK=false
SECRET_EXPOSURE_MARKER_PATH=data/compromised_secret.marker

INITIAL_CAPITAL=1000.0
MAX_DRAWDOWN_PCT=10
RISK_PER_TRADE_PCT=1
MAX_POSITION_SIZE_PCT=20

KRAKEN_API_KEY=
KRAKEN_API_SECRET=
```

> Important: `PREFLIGHT_ONLY=true` valide uniquement les garde-fous et checks de sécurité au démarrage. Cela **n'active pas** un trading paper continu.

## Erreurs d’attestation fréquentes
- `DASHBOARD_API_TOKEN`: absent, vide, ou laissé avec une valeur non conforme à la politique de déploiement.
- `LEAKED_SSH_KEY_ROTATED_ACK`: mis à `true` sans preuve de rotation opérationnelle des secrets, ou incohérent avec l'état réel de sécurité.
- Credentials Kraken (`KRAKEN_API_KEY`, `KRAKEN_API_SECRET`): manquants/invalides quand requis par le scénario de validation de connectivité exchange.
- Rappel: avec `PREFLIGHT_ONLY=true`, l'attestation couvre les checks de sécurité et de configuration, pas l'exécution d'une session paper en continu.

## Paper-trading operations helpers
- Validate paper launch config: `python tools/paper_ops.py validate --env-file .env`
- Print start/run checklist: `python tools/paper_ops.py start-guide`
- Print paper feature-flag matrix: `python tools/paper_ops.py flags-guide`
- Generate post-run session summary: `python tools/paper_ops.py session-summary --log-file autobot_async.log --hours 24 --format markdown`

Detailed guide: `docs/PAPER_TRADING_OPERATIONS.md`.

## Mode live
Voir `docs/LIVE_PROMOTION_GATES.md`, `SECURITY.md`, `RUNBOOK.md`.

## Healthcheck Docker (TLS vs endpoint interne)
Le conteneur supporte **2 modes explicites** pour `/health`:

| Contexte | Mode recommandé | Configuration | Comportement |
|---|---|---|---|
| Local/dev/paper sur réseau Docker privé | `internal_http` (défaut) | `HEALTHCHECK_MODE=internal_http` | Le healthcheck interroge `http://127.0.0.1:8080/health` (loopback interne au conteneur, sans TLS). |
| Production avec terminaison TLS dans l'app | `tls` | `HEALTHCHECK_MODE=tls` + `HEALTHCHECK_CA_CERT=/app/certs/ca.crt` | Le healthcheck interroge `https://localhost:8080/health` avec validation CA stricte via `--cacert` (pas de `-k`). |

Exemple production:
```bash
HEALTHCHECK_MODE=tls
HEALTHCHECK_CA_CERT=/app/certs/ca.crt
```

## Contribution policy
- Do not commit build outputs (`dashboard/dist/`) or dependencies (`dashboard/node_modules/`).
- Frontend artifacts must be generated during CI/CD builds (GitHub Actions/Netlify), not versioned in Git.
