# Guide de Connexion à AUTOBOT

Ce guide explique comment se connecter à l'application AUTOBOT et accéder aux différentes interfaces utilisateur.

## Prérequis

- Avoir une clé de licence valide (fournie par l'administrateur)
- Disposer d'identifiants utilisateur (nom d'utilisateur et mot de passe)
- Accès au serveur où AUTOBOT est déployé

## Méthodes de Connexion

### 1. Connexion via l'Interface Web

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

### 2. Accès aux Différentes Interfaces

Une fois connecté, vous pouvez accéder aux différentes interfaces :

- **Dashboard Simplifié** : `/simple/`
- **Dashboard Mobile** : `/mobile/`
- **Documentation API** : `/docs/`

### 3. Connexion via API (pour les développeurs)

Pour les intégrations programmatiques, vous pouvez obtenir un token JWT via l'API :

```bash
curl -X POST "http://[adresse-du-serveur]/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=votre_utilisateur&password=votre_mot_de_passe&grant_type=password"
```

La réponse contiendra un token JWT que vous pourrez utiliser pour les requêtes ultérieures :

```bash
curl -X GET "http://[adresse-du-serveur]/api/mobile/detect" \
  -H "Authorization: Bearer votre_token_jwt" \
  -H "Accept: application/json"
```

## Résolution des Problèmes Courants

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

## Déconnexion

Pour vous déconnecter, accédez à l'URL :
```
http://[adresse-du-serveur]/logout
```

Cela supprimera votre token d'authentification et vous redirigera vers la page de connexion.
