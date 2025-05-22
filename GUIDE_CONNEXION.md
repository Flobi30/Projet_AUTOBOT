# Guide de Connexion à AUTOBOT

Ce guide explique comment configurer, se connecter à l'application AUTOBOT et accéder aux différentes interfaces utilisateur.

## 1. Configuration initiale

Avant de pouvoir utiliser AUTOBOT, vous devez configurer les variables d'environnement dans le fichier `.env`:

```
# JWT Authentication
JWT_SECRET_KEY=votre_clé_secrète_jwt
JWT_ALGORITHM=HS256
TOKEN_EXPIRE_MINUTES=1440

# Admin Credentials
ADMIN_USER=votre_nom_utilisateur
ADMIN_PASSWORD=votre_mot_de_passe_fort

# Clés API pour les services
ALPHA_KEY=ta_cle_alpha
TWELVE_KEY=ta_cle_twelve
FRED_KEY=ta_cle_fred
NEWSAPI_KEY=ta_cle_news
SHOPIFY_KEY=ta_cle_shopify
SHOPIFY_SHOP_NAME=nom_de_ton_shop

# Clé de licence AUTOBOT
LICENSE_KEY=AUTOBOT-12345678-ABCDEFGH-IJKLMNOP-QRSTUVWX

# Environment
ENVIRONMENT=development  # Changer en "production" pour le déploiement
```

## 2. Prérequis

- Avoir une clé de licence valide (fournie par l'administrateur)
- Disposer d'identifiants utilisateur (nom d'utilisateur et mot de passe)
- Accès au serveur où AUTOBOT est déployé

## 3. Méthodes de Connexion

### 3.1 Connexion via l'Interface Web

La méthode la plus simple pour accéder à AUTOBOT est d'utiliser l'interface de connexion web :

1. Ouvrez votre navigateur et accédez à l'URL du serveur AUTOBOT
   ```
   http://[adresse-du-serveur]/login
   ```

2. Sur la page de connexion, saisissez :
   - Votre nom d'utilisateur
   - Votre mot de passe
   - Votre clé de licence

3. Cliquez sur le bouton "Se connecter"

4. Vous serez automatiquement redirigé vers le dashboard simplifié

### 3.2 Accès aux Différentes Interfaces

Une fois connecté, vous pouvez accéder aux différentes interfaces :

- **Dashboard Simplifié** : `/simple/`
- **Dashboard Mobile** : `/mobile/`
- **Documentation API** : `/docs/`

### 3.3 Connexion via API (pour les développeurs)

Pour les intégrations programmatiques, vous pouvez obtenir un token JWT via l'API :

```bash
curl -X POST "http://[adresse-du-serveur]/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=votre_utilisateur&password=votre_mot_de_passe"
```

La réponse contiendra un token JWT que vous pourrez utiliser pour les requêtes ultérieures :

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```

Utilisez ce token pour les requêtes API :

```bash
curl -X GET "http://[adresse-du-serveur]/api/mobile/detect" \
  -H "Authorization: Bearer votre_token_jwt" \
  -H "Accept: application/json"
```

## 4. Lancement d'AUTOBOT

### 4.1 Mode Backtest

Pour lancer AUTOBOT en mode backtest (test de stratégies) :

```bash
python -m src.autobot.main --mode backtest --strategy nom_strategie --period 30d
```

Options disponibles :
- `--strategy` : Nom de la stratégie à tester
- `--period` : Période de backtest (ex: 30d, 60d, 90d)
- `--symbol` : Paire de trading (ex: BTC/USDT)

### 4.2 Mode Production

Pour lancer AUTOBOT en mode production (trading réel) :

```bash
python -m src.autobot.main --mode production --strategy nom_strategie
```

Options disponibles :
- `--strategy` : Nom de la stratégie à utiliser
- `--symbol` : Paire de trading (ex: BTC/USDT)
- `--risk` : Niveau de risque (1-10)

Vous pouvez également lancer AUTOBOT via l'interface web en accédant à la section "Paramètres" et en sélectionnant le mode souhaité.

## 5. Protection CSRF

AUTOBOT implémente une protection CSRF (Cross-Site Request Forgery) pour sécuriser les formulaires. Lors de l'utilisation de l'API pour soumettre des formulaires, vous devez inclure un token CSRF :

1. Récupérez d'abord le token CSRF depuis un cookie :
```bash
curl -c cookies.txt "http://[adresse-du-serveur]/login"
```

2. Utilisez ce token dans vos requêtes POST :
```bash
curl -X POST "http://[adresse-du-serveur]/login" \
  -b cookies.txt \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -H "X-CSRF-Token: $(grep csrf_token cookies.txt | awk '{print $7}')" \
  -d "username=votre_utilisateur&password=votre_mot_de_passe&license_key=votre_cle_licence&csrf_token=$(grep csrf_token cookies.txt | awk '{print $7}')"
```

### 5.1 Connexion automatisée via script

Pour automatiser le processus de connexion, vous pouvez utiliser le script `login.sh` fourni dans le répertoire `scripts/` :

```bash
# Configurer les variables dans le script
nano scripts/login.sh

# Rendre le script exécutable
chmod +x scripts/login.sh

# Exécuter le script
./scripts/login.sh
```

Le script effectue automatiquement les opérations suivantes :
1. Récupère la page de login et sauvegarde les cookies
2. Extrait le token CSRF de la page HTML
3. Soumet le formulaire avec tous les champs requis, y compris le token CSRF
4. Vérifie la redirection et l'accès au dashboard

### 5.2 Connexion via API

Pour les appels API, vous pouvez utiliser l'en-tête `Content-Type: application/json` pour contourner la validation CSRF :

```bash
curl -X POST "http://[adresse-du-serveur]/login" \
  -H "Content-Type: application/json" \
  -d '{"username":"votre_utilisateur","password":"votre_mot_de_passe","license_key":"votre_cle_licence"}'
```

## 6. Résolution des Problèmes Courants

### Erreur "Not authenticated"

Si vous recevez une erreur "Not authenticated", vérifiez que :
- Votre token JWT n'a pas expiré
- Vous avez correctement inclus le header `Authorization: Bearer <token>`
- Votre clé de licence est valide

### Erreur "Invalid credentials"

Si vous recevez une erreur "Invalid credentials", vérifiez que :
- Votre nom d'utilisateur est correct
- Votre mot de passe est correct

### Erreur "Invalid license key"

Si vous recevez une erreur "Invalid license key", vérifiez que :
- Votre clé de licence est correctement saisie
- Votre clé de licence n'a pas expiré
- Contactez l'administrateur pour obtenir une nouvelle clé

### Erreur "CSRF token manquant ou invalide"

Si vous recevez une erreur concernant le token CSRF, vérifiez que :
- Vous avez bien récupéré le token CSRF depuis le cookie
- Vous avez inclus le token dans l'en-tête `X-CSRF-Token`
- Vous avez inclus le token dans les données du formulaire

## 7. Déconnexion

Pour vous déconnecter, accédez à l'URL :
```
http://[adresse-du-serveur]/logout
```

Cela supprimera votre token d'authentification et vous redirigera vers la page de connexion.

## 8. Orchestration 100% UI — "No-Touch" AUTOBOT

AUTOBOT propose désormais une orchestration 100% UI qui ne nécessite aucune interaction avec le terminal. Voici comment utiliser cette nouvelle fonctionnalité :

### 8.1 Configuration initiale

1. Accédez à la page de configuration à l'adresse : `http://localhost:8000/setup`
2. Remplissez tous les champs requis :
   - Clés API (Alpha, Twelve, Fred, NewsAPI, Shopify, OLLAMA)
   - Clé de licence
   - JWT Secret Key et algorithme
   - Identifiants administrateur
3. Cliquez sur "Valider et Démarrer AUTOBOT"
4. Le système validera toutes les clés et, si tout est correct, démarrera automatiquement les backtests

### 8.2 Backtests automatiques

Une fois la configuration validée, vous serez redirigé vers la page des backtests :

1. Configurez les seuils de performance souhaités :
   - Sharpe Ratio minimum
   - Drawdown maximum
   - P&L minimum
2. Activez l'option "Auto-Live" si vous souhaitez un passage automatique en production
3. Les backtests démarrent et s'exécutent automatiquement
4. Vous pouvez suivre leur progression en temps réel

### 8.3 Passage en production

Lorsque tous les backtests atteignent les seuils définis :

1. Si l'option "Auto-Live" est activée, le système passe automatiquement en mode production
2. Sinon, un bouton "Passer en Production" apparaît, vous permettant de décider quand effectuer la transition
3. Après le passage en production, vous êtes redirigé vers la page des opérations

### 8.4 Opérations (Trading Live + Backtests continus)

La page des opérations vous permet de :

1. Suivre les performances du trading en temps réel
2. Consulter le journal des ordres
3. Activer/désactiver les backtests continus qui affinent les stratégies
4. Visualiser les améliorations apportées par les backtests continus

### 8.5 Ghosting / Duplication d'instances

La page de ghosting vous permet de :

1. Configurer le nombre maximum d'instances
2. Choisir le mode d'évasion (user-agent, IP-rotation, delay random)
3. Gérer les instances (pause, reprise, arrêt)
4. Suivre les performances des instances dupliquées

### 8.6 Gestion des licences

La page de licence vous permet de :

1. Vérifier le statut de votre licence
2. Consulter les détails (type, nombre d'instances autorisées, date d'expiration)
3. Appliquer une nouvelle clé de licence si nécessaire

### 8.7 Logs & Monitoring

La page des logs vous permet de :

1. Filtrer les logs par type (Backtest, Live, Ghosting, Système)
2. Visualiser les statistiques et graphiques
3. Télécharger les logs au format CSV

Cette orchestration 100% UI élimine complètement le besoin d'utiliser des commandes CLI, rendant AUTOBOT plus accessible et plus facile à utiliser.
