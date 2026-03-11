# AUTOBOT V2 - Démarrage avec Dashboard

## 🔒 Sécurité

**Important :** L'API Dashboard est maintenant sécurisée :
- Bind sur `127.0.0.1` (localhost uniquement) par défaut
- Authentification optionnelle via token (`DASHBOARD_API_TOKEN`)
- L'endpoint `POST /api/emergency-stop` nécessite une confirmation explicite

## 🚀 Démarrage Rapide

### Option 1: Tout démarrer en une commande

```bash
./start-autobot.sh
```

Cela démarre :
- Le bot Python (API sur http://localhost:8080)
- Le dashboard React (sur http://localhost:5173)

### Option 2: Démarrer séparément

**Terminal 1 - Le bot :**
```bash
pip install -r src/autobot/v2/api/requirements.txt
python src/autobot/v2/main.py
```

**Terminal 2 - Le dashboard :**
```bash
cd dashboard
npm install
npm run dev
```

## 📊 Accès

| Service | URL | Description |
|---------|-----|-------------|
| Dashboard | http://localhost:5173 | Interface React |
| API Bot | http://localhost:8080/api/status | Statut du bot |
| API Docs | http://localhost:8080/docs | Documentation FastAPI |

## 🔧 Configuration sécurisée

Créez un fichier `.env` à la racine :

```bash
# Kraken API (obligatoire pour trading réel)
KRAKEN_API_KEY=votre_clé
KRAKEN_API_SECRET=votre_secret

# Dashboard API Token (optionnel mais recommandé)
# Si défini, le dashboard nécessite ce token
DASHBOARD_API_TOKEN=votre_token_secret_aléatoire
```

### Utilisation du token

Si `DASHBOARD_API_TOKEN` est défini, toutes les requêtes API doivent inclure :
```
Authorization: Bearer votre_token_secret_aléatoire
```

## 🛠️ Prérequis

### Python
```bash
pip install -r src/autobot/v2/api/requirements.txt
```

### Node.js
```bash
cd dashboard
npm install
```

## 🛑 Arrêt

```bash
./stop-autobot.sh
```

Ou manuellement :
- `Ctrl+C` dans les terminaux
- `pkill -f python.*autobot`

## 📁 Structure

```
.
├── src/autobot/v2/
│   ├── main.py                 # Point d'entrée
│   ├── orchestrator.py         # Gestion multi-instance
│   ├── api/
│   │   └── dashboard.py        # API FastAPI
│   └── strategies/
│       ├── grid.py
│       └── trend.py
├── dashboard/                   # React + Vite
│   ├── src/
│   │   ├── App.tsx
│   │   └── pages/
│   └── package.json
├── start-autobot.sh
└── stop-autobot.sh
```

## 🔌 Connexion Dashboard ↔ Bot

Le dashboard React se connecte automatiquement à l'API du bot sur `http://localhost:8080`.

Les données sont synchronisées en temps réel via les endpoints :
- `GET /api/status` - Statut global
- `GET /api/instances` - Liste des instances
- `GET /api/instances/{id}/positions` - Positions ouvertes
- `POST /api/emergency-stop` - Arrêt d'urgence (⚠️ nécessite confirmation)

### Exemple requête API

```bash
# Sans authentification (mode dev)
curl http://localhost:8080/api/status

# Avec authentification (mode production)
curl -H "Authorization: Bearer $DASHBOARD_API_TOKEN" \
  http://localhost:8080/api/status

# Arrêt d'urgence (avec confirmation)
curl -X POST \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $DASHBOARD_API_TOKEN" \
  -d '{"confirmation":"CONFIRM_STOP"}' \
  http://localhost:8080/api/emergency-stop
```

## 🐛 Débogage

**Vérifier que l'API fonctionne :**
```bash
curl http://localhost:8080/api/status
```

**Voir les logs :**
```bash
tail -f autobot.log
```

**Redémarrer proprement :**
```bash
./stop-autobot.sh
./start-autobot.sh
```
