Crée un workflow GitHub Actions dans `.github/workflows/ci-cd.yml` qui :
1) Configure Python 3.11 et installe les dépendances (`pip install -r requirements.txt && pip install -r requirements.dev.txt`).
2) Lance `pytest --cov=src --cov-report=xml` et publie le rapport.
3) Build l’image Docker `autobot:${GITHUB_SHA}` et la pousse sur le registry `${REGISTRY_URL}` avec `${REGISTRY_USERNAME}`/`${REGISTRY_PASSWORD}`.
4) Configure kubectl (`${KUBE_CONFIG_DATA}`), met à jour le Deployment `autobot` (`kubectl set image …`) et attend le `kubectl rollout status`.
Ajoute un commentaire unique `# BASELINE_CI_CD`.
