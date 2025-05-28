# AUTOBOT - Guide d'Installation et d'Utilisation

## Vue d'ensemble

AUTOBOT est une plateforme avancée d'automatisation de trading et d'e-commerce qui utilise l'intelligence artificielle pour maximiser les profits. Le système comprend plusieurs modules intégrés :

- **Trading automatisé** avec stratégies prédictives et apprentissage par renforcement
- **Orchestrateur multi-agent** avec intégration SuperAGI
- **Module e-commerce** pour la gestion des invendus et l'optimisation des prix
- **Système HFT** (High-Frequency Trading) avec duplication d'instances contrôlée
- **Interface utilisateur** responsive pour PC et mobile

## Prérequis

- Python 3.8 ou supérieur
- Docker et Docker Compose (recommandé pour le déploiement)
- Accès à Internet pour les connexions API
- Clé de licence AUTOBOT valide

## Installation

### Option 1: Installation directe

1. Clonez le dépôt :
   ```
   git clone https://github.com/Flobi30/Projet_AUTOBOT.git
   cd Projet_AUTOBOT
   ```

2. Installez les dépendances :
   ```
   pip install -r requirements.txt
   ```

3. Configurez votre environnement :
   ```
   cp .env.example .env
   ```
   Éditez le fichier `.env` avec vos informations personnelles et clés API.

4. Lancez l'application :
   ```
   python -m src.autobot.main
   ```

### Option 2: Installation avec Docker (recommandée)

1. Clonez le dépôt :
   ```
   git clone https://github.com/Flobi30/Projet_AUTOBOT.git
   cd Projet_AUTOBOT
   ```

2. Configurez votre environnement :
   ```
   cp .env.example .env
   ```
   Éditez le fichier `.env` avec vos informations personnelles et clés API.

3. Construisez et lancez les conteneurs :
   ```
   docker-compose up -d
   ```

4. Accédez à l'interface web :
   ```
   http://localhost:8000
   ```

## Configuration

### Clés API requises

AUTOBOT nécessite plusieurs clés API pour fonctionner correctement. Vous pouvez les configurer directement depuis l'interface utilisateur dans la section "Paramètres" ou les ajouter au fichier `.env` :

1. **Échanges de cryptomonnaies** (au moins un requis) :
   - Binance
   - Coinbase Pro
   - Kraken
   - FTX

2. **Plateformes e-commerce** (optionnel) :
   - Shopify
   - Amazon
   - eBay
   - WooCommerce

3. **Services d'IA** (optionnel pour fonctionnalités avancées) :
   - OpenAI
   - HuggingFace

### Système de licence

AUTOBOT utilise un système de licence avancé qui permet de contrôler l'accès et les fonctionnalités :

1. **Activation de licence** :
   - Accédez à la page "Paramètres" > "Licence"
   - Entrez votre clé de licence
   - Cliquez sur "Activer"

2. **Partage avec des amis** :
   - Accédez à la page "Paramètres" > "Licence" > "Partage"
   - Créez une clé de partage pour chaque ami
   - Définissez les limites et permissions pour chaque clé
   - Envoyez la clé à votre ami

3. **Utilisation multi-appareils** :
   - La même clé de licence peut être utilisée sur plusieurs appareils
   - Connectez-vous avec les mêmes identifiants sur chaque appareil
   - Toutes vos données et configurations seront synchronisées

## Utilisation

### Dashboard

Le dashboard principal vous donne une vue d'ensemble de votre portfolio, des performances de trading, et des opportunités e-commerce. Vous pouvez :

- Visualiser la valeur totale de votre portfolio
- Suivre les performances des stratégies de trading
- Voir les transactions récentes
- Surveiller les agents IA actifs
- Accéder aux opportunités d'e-commerce

### Module de Trading

Le module de trading vous permet de :

- Créer et configurer des stratégies de trading
- Effectuer des backtests sur des données historiques
- Activer/désactiver des stratégies
- Suivre les performances en temps réel
- Configurer les paramètres de risque

### Apprentissage par Renforcement (RL)

Le module RL vous permet de :

- Créer et entraîner des modèles d'IA
- Configurer les paramètres d'apprentissage
- Suivre les progrès de l'entraînement
- Déployer des modèles entraînés
- Analyser les performances des modèles

### Agents IA

Le module d'agents IA vous permet de :

- Configurer différents types d'agents spécialisés
- Orchestrer la communication entre agents
- Surveiller les performances des agents
- Ajouter de nouvelles capacités aux agents
- Optimiser l'allocation des ressources

### E-commerce

Le module e-commerce vous permet de :

- Synchroniser l'inventaire avec vos plateformes
- Identifier les produits invendus
- Optimiser les prix pour maximiser les profits
- Commander directement des produits à prix réduits
- Suivre les performances de vos ventes

## Fonctionnalités avancées

### High-Frequency Trading (HFT)

Le module HFT permet d'exécuter des transactions à haute fréquence avec :

- Pipeline ultra-basse latence
- Exécution d'ordres en parallèle
- Gestion fine des risques
- Duplication d'instances contrôlée (ghosting)
- Optimisation des performances

Pour activer le HFT :
1. Accédez à "Trading" > "Paramètres avancés" > "HFT"
2. Configurez les paramètres de performance
3. Définissez les limites de risque
4. Activez le mode HFT

### Duplication d'instances (Ghosting)

La fonctionnalité de ghosting permet de dupliquer des instances AUTOBOT pour augmenter les capacités de trading :

1. Accédez à "Paramètres" > "Système" > "Ghosting"
2. Configurez le nombre d'instances souhaité
3. Définissez les marchés et stratégies pour chaque instance
4. Activez le ghosting

### SuperAGI Integration

L'intégration avec SuperAGI permet d'orchestrer des agents IA avancés :

1. Accédez à "Agents" > "SuperAGI"
2. Configurez les agents spécialisés
3. Définissez les objectifs et contraintes
4. Activez l'orchestrateur SuperAGI

## Dépannage

### Problèmes courants

1. **Erreur de connexion API** :
   - Vérifiez que vos clés API sont correctement configurées
   - Assurez-vous que votre connexion Internet fonctionne
   - Vérifiez que le service API est disponible

2. **Performances lentes** :
   - Vérifiez les ressources système disponibles
   - Réduisez le nombre d'agents actifs
   - Optimisez les paramètres de performance

3. **Erreur de licence** :
   - Vérifiez que votre licence est active et valide
   - Assurez-vous que vous n'avez pas dépassé les limites de votre licence
   - Contactez le support si le problème persiste

### Support

Pour obtenir de l'aide supplémentaire :

- Consultez la documentation complète dans le dossier `docs/`
- Visitez le forum d'aide à [forum.autobot.ai](https://forum.autobot.ai)
- Contactez le support à [support@autobot.ai](mailto:support@autobot.ai)

## Mise à jour

Pour mettre à jour AUTOBOT vers la dernière version :

### Installation directe :
```
git pull
pip install -r requirements.txt
```

### Installation Docker :
```
git pull
docker-compose down
docker-compose build
docker-compose up -d
```

## Sécurité

AUTOBOT prend la sécurité au sérieux :

- Toutes les données sensibles sont chiffrées
- Les communications API utilisent HTTPS
- L'authentification utilise JWT avec expiration
- Les clés API sont stockées de manière sécurisée
- Des audits de sécurité réguliers sont effectués

## Optimisation des profits

Pour maximiser vos profits avec AUTOBOT :

1. **Commencez petit** : Débutez avec un capital modeste (500€) pour tester le système
2. **Diversifiez** : Utilisez à la fois le trading et l'e-commerce
3. **Réinvestissez** : Configurez le réinvestissement automatique des profits
4. **Optimisez** : Ajustez régulièrement vos stratégies en fonction des performances
5. **Scalez** : Augmentez progressivement votre capital et le nombre d'instances

## Licence

AUTOBOT est distribué sous licence propriétaire. Voir le fichier `LICENSE` pour plus de détails.

---

© 2025 AUTOBOT. Tous droits réservés.
