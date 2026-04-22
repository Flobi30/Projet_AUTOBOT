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
