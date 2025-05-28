#!/usr/bin/env python3
"""
Orchestrateur complet pour Projet_AUTOBOT
— audit IA & génération stubs
— tests plugins & endpoints
— build & run Docker
— déploiement Kubernetes + health‑check
"""

import subprocess
import sys
import time

def run(cmd, **kwargs):
    print(f"\n»» Exécution: {cmd}")
    subprocess.run(cmd, shell=True, check=True, **kwargs)

def main():
    # 1) Audit & génération stubs
    run("python scripts/full_pipeline.py --top-n 30 --use-gpt")

    # 2) Tests unitaires sur les stubs
    run("pytest tests/test_plugins.py -q")

    # 3) Tests des endpoints métier (backtest, train, metrics, logs)
    run("pytest tests/test_backtest_endpoint.py tests/test_train_endpoint.py "
        "tests/test_metrics_endpoint.py tests/test_logs_endpoint.py -q")

    # 4) Tests globaux
    run("pytest -q")

    # 5) Build Docker
    run("docker build -t autobot:latest .")

    # 6) Run container pour health‑check
    # on démarre en arrière‑plan
    run("docker rm -f autobot_test || true")
    run("docker run -d --name autobot_test -p 8000:8000 autobot:latest")
    print("⏳ Attente 5s pour que l’API démarre…")
    time.sleep(5)
    # health‑check
    run("curl -f http://localhost:8000/health")

    # Stop container de test
    run("docker stop autobot_test")

    # 7) Déploiement Kubernetes
    run("kubectl apply -f k8s/deployment.yaml")
    run("kubectl apply -f k8s/service.yaml")
    run("kubectl apply -f k8s/hpa.yaml")
    run("kubectl rollout status deployment/autobot")

    print("\n✅ Orchestration terminée avec succès !")

if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as e:
        print(f"\n❌ Erreur ({e.returncode}) lors de : {e.cmd}", file=sys.stderr)
        sys.exit(e.returncode)
