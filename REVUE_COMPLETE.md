# 🔍 REVUE COMPLÈTE - AUTOBOT V2
## Date: 2026-04-06
## Serveur: Hetzner CAX11 (178.104.0.255)

---

## 🟢 CE QUI FONCTIONNE

| Composant | Statut | Notes |
|-----------|--------|-------|
| Déploiement Docker | ✅ | Multi-stage build OK |
| WebSocket Kraken | ✅ | Connecté, reçoit XBT/EUR |
| Orchestrateur Async | ✅ | uvloop, asyncio OK |
| API Dashboard | ✅ | Endpoints /api/* opérationnels |
| Health checks | ✅ | Docker healthcheck OK |
| Structure modules | ✅ | 30+ modules performance chargés |

---

## 🔴 PROBLÈMES CRITIQUES (P0)

### 1. Aucun trade exécuté en 3+ jours
**Fichier:** 
**Problème:** La stratégie Grid ne place pas d ordres
**Cause probable:** 
- Prix actuel BTC hors de la range configurée (±7% de 50,000€)
- Ou logique d initialisation bloquée
- Ou paper trading non détecté

**Correction suggérée:**
- Rendre le center_price dynamique (dernier prix connu)
- Ajouter un log de debug quand les niveaux sont calculés

---

### 2. Dashboard Capital - Données 100% mockées
**Fichier:** 
**Problèmes:**
- Valeurs hardcodées: 5,420€, 1,285€, etc.
- Transactions mockées en dur (recentTransactions)
- Stripe non fonctionnel (fausse clé VITE_STRIPE_PUBLIC_KEY)
- Aucun appel API vers le backend

---

### 3. Dashboard LiveTrading - Graphique mocké
**Fichier:** 
**Problème:** portfolioData avec données simulées
**Solution:** Créer un endpoint 

---

### 4. Paper Trading - Détection incertaine
**Fichier:** 
**Problème:** PAPER_TRADING=true dans .env mais pas sûr qu il soit utilisé

---

## 🟡 PROBLÈMES MOYENS (P1)

### 5. Risk Manager - Warning coroutine
**Fichier:** 
**Problème:** RuntimeWarning sur emergency_stop_all coroutine non awaitée
**Correction:** Ajouter await ligne ~244

### 6. Instance Capital - Source incertaine
Capital Kraken réel (0€) vs Paper trading (1000€) - à clarifier

### 7. Pas de persistance des trades
SQLite existe mais pas de table trades visible

---

## 🔵 AMÉLIORATIONS SUGGÉRÉES (P2)

### 9. Stratégie Grid - Paramètres
- Réduire num_levels de 15 à 5-7 pour commencer
- Ajuster range_percent selon volatilité actuelle BTC
- Rendre center_price dynamique

### 10. Dashboard - Endpoints manquants
Créer:
-  - Capital détaillé
-  - Historique capital
-  - Liste des trades
-  - PF, Sharpe, win rate

---

## 📋 CHECKLIST AVANT LIVE

- [ ] Au moins 1 trade exécuté en paper trading
- [ ] Dashboard affiche des données réelles (pas mock)
- [ ] PF > 1.0 sur 48h de paper trading
- [ ] KYC Kraken validé

---

## 🎯 PROCHAINES ACTIONS

1. **Identifier pourquoi Grid ne trade pas**
2. **Connecter Dashboard Capital à l'API**
3. **Connecter Dashboard LiveTrading à l'API**
4. **Créer endpoint /api/history pour le graphique**
5. **Tester 1 trade manuellement**

---

*Document généré automatiquement - Session revue 2026-04-06*
