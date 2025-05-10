# DEPLOY_DOCKER
Crée un script Bash `scripts/deploy.sh` :
1. `docker build -t ${REGISTRY_URL}/autobot:${GITHUB_SHA} .`
2. `echo "$REGISTRY_PASSWORD" | docker login $REGISTRY_URL -u "$REGISTRY_USERNAME" --password-stdin`
3. `docker push ${REGISTRY_URL}/autobot:${GITHUB_SHA}`
