# DEPLOY_K8S
Crée un script Bash `scripts/deploy_k8s.sh` :
1. `echo "$KUBE_CONFIG_DATA" | base64 --decode > $HOME/.kube/config`
2. `kubectl set image deployment/autobot autobot=${REGISTRY_URL}/autobot:${GITHUB_SHA} --record`
3. `kubectl rollout status deployment/autobot`
