Voici un exemple de script `deploy_k8s.sh` qui utilise `kubectl` pour mettre à jour l'image d'un déploiement Kubernetes et vérifier le statut du déploiement après la mise à jour. Ce script prend en paramètres le nom du déploiement, le nom de l'image et le namespace (facultatif).

```bash
#!/bin/bash

# Vérification des arguments
if [ "$#" -lt 2 ]; then
    echo "Usage: $0 <deployment-name> <new-image> [namespace]"
    exit 1
fi

DEPLOYMENT_NAME=$1
NEW_IMAGE=$2
NAMESPACE=${3:-default}  # Utilise 'default' si aucun namespace n'est spécifié

# Mettre à jour l'image du déploiement
echo "Mise à jour de l'image du déploiement '$DEPLOYMENT_NAME' vers '$NEW_IMAGE' dans le namespace '$NAMESPACE'..."
kubectl set image deployment/$DEPLOYMENT_NAME *=$NEW_IMAGE -n $NAMESPACE

# Vérifier le statut du déploiement
echo "Vérification du statut du déploiement '$DEPLOYMENT_NAME'..."
kubectl rollout status deployment/$DEPLOYMENT_NAME -n $NAMESPACE

# Vérification du succès de la mise à jour
if [ $? -eq 0 ]; then
    echo "Mise à jour réussie de l'image du déploiement '$DEPLOYMENT_NAME'."
else
    echo "Échec de la mise à jour de l'image du déploiement '$DEPLOYMENT_NAME'."
    exit 1
fi
```

### Instructions pour utiliser le script :

1. **Créer le fichier** :
   Créez un fichier nommé `deploy_k8s.sh` et copiez-y le contenu ci-dessus.

2. **Rendre le script exécutable** :
   Exécutez la commande suivante pour rendre le script exécutable :
   ```bash
   chmod +x deploy_k8s.sh
   ```

3. **Exécuter le script** :
   Vous pouvez exécuter le script en fournissant le nom du déploiement, la nouvelle image et éventuellement le namespace :
   ```bash
   ./deploy_k8s.sh <deployment-name> <new-image> [namespace]
   ```

### Exemple d'utilisation :
```bash
./deploy_k8s.sh my-deployment my-image:latest my-namespace
```

Ce script met à jour l'image du déploiement spécifié et affiche le statut du déploiement après la mise à jour.