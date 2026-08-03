# AUTOBOT Bloc 6 — probe de preuve runtime (2026-08-03)

## Constat

Après le retour du VPS, le rebuild contrôlé a recréé le conteneur sur
`c23db09`. Le script de preuve runtime a ensuite échoué avant d'émettre une
preuve : son `docker exec` essayait d'importer `autobot` depuis `/app`, alors
que l'image conserve le package sous `/app/src`.

## Correctif

Le probe de fonctions d'autorisation pures s'exécute désormais avec
`docker exec --workdir /app/src`. Il reste sans réseau, sans lecture de secret,
sans ouverture de base et sans appel d'ordre. Ce changement ne modifie aucun
flag d'exécution ni le processus AUTOBOT déjà en cours.

## Validation locale

```text
bash -n deploy/verify-autobot-runtime-evidence.sh
python -m pytest tests/test_deployment_runtime_evidence.py \
  tests/test_deployment_safety_invariants.py \
  tests/test_docker_build_provenance.py -q
git diff --check
```

Résultat : `8 passed`.

## Suite

Redéployer ce seul correctif avec le rebuild contrôlé, puis exécuter
`deploy/verify-autobot-runtime-evidence.sh`. Une preuve est acceptée seulement
si commit GitHub, checkout VPS et image Docker correspondent, avec health,
WebSocket et verrou research-only confirmés.
