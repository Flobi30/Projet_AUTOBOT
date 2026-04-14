# RUNBOOK (micro-live)

1. Vérifier absence du marker compromis (`data/compromised_secret.marker`).
2. Exécuter préflight (`PREFLIGHT_ONLY=true`).
3. Vérifier attestation OK dans les logs.
4. Démarrer en `DEPLOYMENT_STAGE=micro_live` avec clé dédiée.
5. Surveiller health, reconciliation, kill switch.
6. Stop propre: arrêter nouvelles actions, attendre in-flight, arrêter orchestrator.
