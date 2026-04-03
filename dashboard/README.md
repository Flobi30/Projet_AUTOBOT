# Dashboard AutoBot V2 — Aperçu

## 🎨 Interface

Le dashboard contient maintenant **5 pages** :

### 1. Live Trading 📈
- Vue temps réel des positions
- Instances actives (Grid, Trend, Mean Reversion)
- P&L en direct
- Contrôles de trading

### 2. Backtest 🧪
- Lancer des backtests
- Historique des résultats
- Comparaison de stratégies

### 3. Capital 💰
- Répartition du capital
- Allocations par instance
- Historique des profits/pertes

### 4. Analytics 📊
- Graphiques de performance
- Profit Factor (PF)
- Sharpe ratio
- Win rate
- Drawdown

### 5. Diagnostic 🏥 **NOUVEAU**
- **Vue d'ensemble santé système**
- Jauges RAM/CPU/Disque (vert/orange/rouge)
- Statut des services (Docker, Kraken API, DB)
- Historique 24h
- **Problèmes détectés automatiquement**
- **Recommandations intelligentes**

---

## 🔍 Page Diagnostic en détail

### Métriques visuelles
```
┌─────────────────┬─────────────────┬─────────────────┐
│     RAM 45%     │     CPU 23%     │   Disque 32%    │
│   [████░░░░░░]  │   [██░░░░░░░░]  │   [███░░░░░░░]  │
│      🟢 OK      │      🟢 OK      │      🟢 OK      │
└─────────────────┴─────────────────┴─────────────────┘
```

### Services surveillés
- **Docker** : Conteneurs actifs
- **Kraken API** : Latence de connexion
- **Base de données** : Taille et état

### Alertes automatiques
```
🚨 CRITIQUE: [
  "RAM: 95% utilisé",
  "Kraken: Timeout"
]

💡 Recommandations: [
  "Réduire MAX_INSTANCES",
  "Vérifier connexion internet"
]
```

### Actions rapides
- Voir logs complets
- Redémarrer le bot
- Backup manuel
- Nettoyer logs

---

## 🚀 Démarrage

```bash
cd dashboard
npm install
npm run dev
```

Puis ouvrir `http://localhost:5173`

---

## 📡 Connexion API

Le dashboard se connecte à l'API du bot sur le port 8080 :

```javascript
// Endpoints utilisés
GET /health              → Statut santé simple
GET /api/performance     → Métriques trading
GET /api/diagnostic      → Diagnostic complet (nouveau)
```

---

## 🎨 Design System

- **Fond** : Gray-900 (`#111827`)
- **Cartes** : Gray-800 avec bordure Gray-700
- **Primaire** : Emerald-500 (vert)
- **Succès** : Green-500
- **Avertissement** : Yellow-500
- **Erreur** : Red-500

### États des composants
- **Healthy** 🟢 : Vert + icône check
- **Warning** 🟡 : Jaune + icône alerte
- **Critical** 🔴 : Rouge + icône croix

---

## 🔧 Développement

### Ajouter un nouvel endpoint
```typescript
// src/pages/Diagnostic.tsx
const fetchDiagnostic = async () => {
  const res = await fetch('/api/diagnostic');
  const data = await res.json();
  setStatus(data);
};
```

### Personnaliser les seuils d'alerte
```typescript
const getStatus = (value: number) => {
  if (value > 90) return 'critical';
  if (value > 80) return 'warning';
  return 'healthy';
};
```
