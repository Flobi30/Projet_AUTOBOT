# Contributing to AUTOBOT

Merci de votre intérêt pour contribuer au projet AUTOBOT ! Ce document fournit des lignes directrices pour contribuer au projet.

## Processus de développement

1. **Fork** le dépôt sur GitHub
2. **Clone** votre fork localement
3. Créez une **branche** pour vos modifications
4. Effectuez vos modifications
5. Exécutez les **tests** pour vous assurer que tout fonctionne
6. **Commit** vos changements
7. **Push** vos changements vers votre fork
8. Soumettez une **Pull Request**

## Structure du projet

Le projet est organisé en plusieurs modules :

```
src/autobot/
├── agents/             # Orchestrateur multi-agent
├── autobot_security/   # Authentification et sécurité
├── ecommerce/          # Gestion d'inventaire e-commerce
├── providers/          # Intégrations avec les échanges
├── rl/                 # Apprentissage par renforcement
├── trading/            # Stratégies et exécution de trading
└── ui/                 # Interface utilisateur
```

## Standards de code

- Utilisez **Python 3.10+**
- Suivez les conventions **PEP 8**
- Écrivez des **tests unitaires** pour toutes les nouvelles fonctionnalités
- Documentez votre code avec des **docstrings**
- Utilisez le **typage** pour améliorer la lisibilité et la maintenabilité

## Tests

Exécutez les tests avant de soumettre une Pull Request :

```bash
pytest tests/
```

## Documentation

Mettez à jour la documentation lorsque vous ajoutez ou modifiez des fonctionnalités :

- **Docstrings** pour les classes et fonctions
- **README.md** pour les changements majeurs
- **Exemples** pour les nouvelles fonctionnalités

## Soumission de Pull Requests

- Créez une branche avec un nom descriptif
- Incluez une description claire de vos changements
- Référencez les issues pertinentes
- Assurez-vous que tous les tests passent
- Attendez la revue de code

## Signalement de bugs

Utilisez les issues GitHub pour signaler des bugs :

- Utilisez un titre clair et descriptif
- Décrivez les étapes pour reproduire le bug
- Incluez des captures d'écran si nécessaire
- Mentionnez votre environnement (OS, version Python, etc.)

## Demande de fonctionnalités

Pour proposer de nouvelles fonctionnalités :

- Expliquez clairement la fonctionnalité proposée
- Décrivez les cas d'utilisation
- Discutez des alternatives envisagées
- Expliquez comment cette fonctionnalité bénéficierait au projet

## Licence

En contribuant à ce projet, vous acceptez que vos contributions soient sous la même licence que le projet.
