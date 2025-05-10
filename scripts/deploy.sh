Voici un exemple de script `deploy.sh` qui construit une image Docker, la tague avec le SHA de GitHub et la pousse vers un registre Docker. Assurez-vous d'avoir les permissions nécessaires pour exécuter ce script et que Docker est installé sur votre machine.

```bash
#!/bin/bash

# Vérifiez si le script est exécuté avec les droits nécessaires
if [ "$EUID" -ne 0 ]; then
  echo "Veuillez exécuter ce script en tant que root ou avec sudo."
  exit 1
fi

# Variables
IMAGE_NAME="votre_nom_d_image"  # Remplacez par le nom de votre image
REGISTRY="votre_registre"        # Remplacez par l'URL de votre registre
GITHUB_SHA=${GITHUB_SHA:-$(git rev-parse HEAD)}  # Récupère le SHA de GitHub ou utilise le SHA actuel du dépôt

# Construire l'image Docker
echo "Construction de l'image Docker..."
docker build -t ${IMAGE_NAME}:${GITHUB_SHA} .

# Taguer l'image
echo "Taguer l'image avec le SHA..."
docker tag ${IMAGE_NAME}:${GITHUB_SHA} ${REGISTRY}/${IMAGE_NAME}:${GITHUB_SHA}

# Pousser l'image vers le registre
echo "Pousser l'image vers le registre..."
docker push ${REGISTRY}/${IMAGE_NAME}:${GITHUB_SHA}

echo "Déploiement terminé avec succès."
```

### Instructions d'utilisation :

1. Remplacez `votre_nom_d_image` par le nom que vous souhaitez donner à votre image Docker.
2. Remplacez `votre_registre` par l'URL de votre registre Docker (par exemple, `docker.io/mon_utilisateur` ou `mon_registre_prive`).
3. Assurez-vous que le script a les permissions d'exécution. Vous pouvez le faire avec la commande suivante :
   ```bash
   chmod +x scripts/deploy.sh
   ```
4. Exécutez le script :
   ```bash
   ./scripts/deploy.sh
   ```

### Remarques :

- Assurez-vous que vous êtes connecté à votre registre Docker avant d'exécuter le script. Vous pouvez le faire avec `docker login`.
- Ce script suppose que vous avez un Dockerfile dans le répertoire courant. Si ce n'est pas le cas, modifiez le chemin dans la commande `docker build`.
- Le script utilise le SHA de la dernière commit Git si la variable d'environnement `GITHUB_SHA` n'est pas définie.