# Guide de Démarrage Rapide AUTOBOT

Ce guide vous aidera à démarrer rapidement avec AUTOBOT après l'installation.

## 1. Premier Lancement

Après avoir installé AUTOBOT (voir `INSTALLATION.md`), lancez l'application:

```bash
python -m autobot.main
```

Accédez à l'interface web: http://localhost:8000

## 2. Configuration Initiale

Lors du premier lancement, vous devrez:

1. **Créer un compte administrateur**
   - Remplissez le formulaire d'inscription
   - Activez votre compte avec la clé de licence

2. **Configurer les connexions aux plateformes**
   - Ajoutez vos clés API pour les plateformes d'échange
   - Testez les connexions

3. **Définir vos préférences**
   - Devise de base
   - Montant d'investissement initial
   - Paramètres de risque

## 3. Modules Principaux

### Module de Trading

1. **Configuration des stratégies**
   - Accédez à "Trading > Stratégies"
   - Activez les stratégies souhaitées
   - Ajustez les paramètres

2. **Backtest**
   - Accédez à "Trading > Backtest"
   - Sélectionnez une stratégie
   - Définissez la période de test
   - Lancez le backtest

3. **Trading en direct**
   - Accédez à "Trading > Live"
   - Activez le trading automatique
   - Surveillez les performances

### Module RL (Apprentissage par Renforcement)

1. **Entraînement**
   - Accédez à "RL > Entraînement"
   - Sélectionnez un modèle
   - Définissez les paramètres
   - Lancez l'entraînement

2. **Déploiement**
   - Accédez à "RL > Modèles"
   - Sélectionnez un modèle entraîné
   - Déployez-le en production

### Module E-commerce

1. **Configuration**
   - Accédez à "E-commerce > Configuration"
   - Connectez vos boutiques en ligne
   - Définissez les règles de prix

2. **Gestion des invendus**
   - Accédez à "E-commerce > Invendus"
   - Visualisez les produits disponibles
   - Configurez les règles de recyclage

## 4. Surveillance et Optimisation

1. **Dashboard**
   - Visualisez les performances en temps réel
   - Suivez les métriques clés

2. **Alertes**
   - Configurez des alertes personnalisées
   - Recevez des notifications

3. **Optimisation**
   - Accédez à "Système > Optimisation"
   - Ajustez les paramètres de performance
   - Activez/désactivez les fonctionnalités

## 5. Modes d'Exécution

AUTOBOT dispose de trois modes principaux:

1. **Mode Standard** (par défaut)
   - Équilibre entre performance et sécurité
   - Adapté à une utilisation quotidienne

2. **Mode Turbo**
   - Maximise les performances
   - Utilise plus de ressources système
   - Idéal pour les périodes de forte volatilité

3. **Mode Ghost**
   - Priorité à l'indétectabilité
   - Réduit l'empreinte numérique
   - Recommandé pour les opérations sensibles

Pour changer de mode:
```bash
python -m autobot.main --mode [standard|turbo|ghost]
```

## 6. Duplication d'Instances

Pour déployer plusieurs instances spécialisées:

1. Accédez à "Système > Instances"
2. Configurez le nombre d'instances par domaine
3. Définissez les limites de ressources
4. Lancez la duplication

## 7. Prochaines Étapes

- Consultez la documentation complète dans le dossier `docs/`
- Explorez les fonctionnalités avancées
- Rejoignez la communauté pour partager vos stratégies
