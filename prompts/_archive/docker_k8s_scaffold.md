# prompts/docker_k8s_scaffold.md
## System
You are a Kubernetes architect.
## User
Generate:
1. Dockerfile (Python 3.11‑slim).
2. docker‑compose.yml for dev.
3. K8s Deployment, Service, HPA manifests.
4. Helm chart skeleton.
## Output
- Dockerfile, docker‑compose.yml
- k8s/deployment.yaml, k8s/service.yaml, k8s/hpa.yaml
- charts/autobot/…
