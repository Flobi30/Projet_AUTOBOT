# RUNBOOK (micro-live)

1. Vérifier absence du marker compromis (`data/compromised_secret.marker`).
2. Exécuter préflight (`PREFLIGHT_ONLY=true`).
3. Vérifier attestation OK dans les logs.
4. Démarrer en `DEPLOYMENT_STAGE=micro_live` avec clé dédiée.
5. Surveiller health, reconciliation, kill switch.
6. Stop propre: arrêter nouvelles actions, attendre in-flight, arrêter orchestrator.

## Table raison attestation → action opérateur

| Raison attestation (stable) | Action opérateur |
| --- | --- |
| `invalid_app_env` / `invalid_deployment_stage` | Corriger les variables `APP_ENV` / `DEPLOYMENT_STAGE`, relancer le préflight. |
| `live_confirmation_missing` / `promotion_gate_failed` | Vérifier la phase de déploiement (`paper`, `micro_live`, `small_live`) puis appliquer les flags requis avant restart. |
| `dashboard_token_missing` / `api_auth_permission_denied` / `orders_endpoint_auth_error` | Régénérer ou recharger les secrets d’authentification API, vérifier les droits de la clé. |
| `risk_limits_missing` | Renseigner `MAX_DRAWDOWN_PCT`, `RISK_PER_TRADE_PCT`, `MAX_POSITION_SIZE_PCT`. |
| `secret_exposure_marker_found` / `compromised_fingerprint_configured` | Procédure incident: rotation des clés, suppression marker seulement après validation sécurité. |
| `shared_api_key_forbidden` / `api_key_assignment_not_dedicated` / `api_key_bot_id_mismatch` | Assigner une clé dédiée par bot/hôte et aligner `UNIQUE_BOT_ID` avec `API_KEY_ASSIGNED_BOT_ID`. |
| `exchange_connectivity_network_error` / `orders_endpoint_network_error` / `clock_drift_network_error` / `reconciliation_network_error` | Vérifier connectivité sortante, DNS, firewall/proxy, status Kraken, puis retenter. |
| `exchange_connectivity_timeout` / `api_auth_timeout` / `orders_endpoint_timeout` / `clock_drift_timeout` / `reconciliation_timeout` | Vérifier latence réseau, saturation runtime, ajuster timeouts si nécessaire. |
| `nonce_io_error` / `db_io_error` / `audit_io_error` / `audit_write_failed` | Vérifier disque/permissions/volume monté, puis valider écriture locale avant relance. |
| `kill_switch_not_initialized` / `kill_switch_already_tripped` | Réinitialiser proprement le kill switch, investiguer pourquoi il est trippé avant redémarrage live. |

## Go/No-Go paper

Avant toute session paper, générer l’attestation artifact :

```bash
python tools/paper_ops.py readiness --artifact-file artifacts/startup_attestation.json --format json
```

Règles de décision à partir de l’artifact JSON (`status`, `reasons`, `diagnostics`) :

- **GO** si `status == "pass"` et `reasons` est vide.
- **NO-GO** si `status == "fail"` ou si `reasons` contient au moins une raison bloquante.
- En cas de **NO-GO**, traiter d’abord les entrées de `diagnostics` avec `status="fail"`, corriger la cause, puis relancer la commande `readiness`.

Exploitation pratique:
- Le script `tools/paper_ops.py readiness` retourne **0** si prêt et **non-zéro** sinon.
- L’artifact `artifacts/startup_attestation.json` est la source de vérité opérateur pour la décision de lancement.
