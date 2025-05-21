# Guide de Connexion à AUTOBOT

Ce guide explique comment configurer, se connecter à l'application AUTOBOT et accéder aux différentes interfaces utilisateur.

## 1. Configuration initiale

Avant de pouvoir utiliser AUTOBOT, vous devez configurer les variables d'environnement dans le fichier `.env`:

```
# JWT Authentication
JWT_SECRET_KEY=7d2915c770e7f462cd48a678f6c624c577bf59b2d06642137ef2b183ea78fa0d
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

### Génération d'une clé JWT sécurisée

Pour une sécurité optimale, il est fortement recommandé de générer une clé JWT forte et unique. Vous pouvez utiliser la commande suivante pour générer une clé de 64 caractères hexadécimaux (32 octets) :

```bash
openssl rand -hex 32
```

Copiez la clé générée et remplacez la valeur de `JWT_SECRET_KEY` dans votre fichier `.env`.

> **IMPORTANT** : Ne partagez jamais votre clé JWT avec des tiers et ne la stockez pas dans des fichiers publics ou des dépôts de code.

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

### Erreur "JWT signature verification failed"

Si vous recevez cette erreur, cela peut indiquer un problème avec la clé JWT :
- Vérifiez que la valeur de `JWT_SECRET_KEY` dans le fichier `.env` est correcte
- Assurez-vous que la même clé est utilisée pour la génération et la vérification des tokens
- Si vous avez récemment changé la clé JWT, tous les tokens précédents seront invalidés

## 7. Déconnexion

Pour vous déconnecter, accédez à l'URL :
```
http://[adresse-du-serveur]/logout
```

Cela supprimera votre token d'authentification et vous redirigera vers la page de connexion.
