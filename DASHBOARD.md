# AUTOBOT V2 - Démarrage avec Dashboard

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

## 🔧 Configuration

Créez un fichier `.env` à la racine :

```bash
# Kraken API (optionnel pour tests)
KRAKEN_API_KEY=votre_clé
KRAKEN_API_SECRET=votre_secret

# Dashboard
DASHBOARD_PORT=5173
API_PORT=8080
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
- `POST /api/emergency-stop` - Arrêt d'urgence

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
