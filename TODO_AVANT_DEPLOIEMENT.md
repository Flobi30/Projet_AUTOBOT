# TODO - Avant déploiement production

## 🔴 CRITIQUE - Bloquant

### 1. Signaux → Exécution (LE PLUS IMPORTANT)
**Problème :** Les stratégies génèrent des `TradingSignal` mais personne ne les écoute !

```python
# Dans grid.py / trend.py
self.emit_signal(signal)  # Le signal part... où ?
```

**Solution :** Créer un `SignalHandler` qui reçoit les signaux et appelle :
- `instance.open_position()` pour BUY
- `instance.close_position()` pour SELL

**Fichier à créer :** `src/autobot/v2/signal_handler.py`

### 2. Capital disponible réel
**Problème :** `_get_available_capital()` retourne toujours 0.0

**Impact :** Les spin-offs (création nouvelles instances à 2000€) ne fonctionnent jamais

**Solution :** Implémenter l'appel API Kraken pour récupérer le vrai solde EUR

### 3. Exécution des ordres
**Problème :** `_cancel_all_orders()` et `_close_all_positions_market()` sont des TODO vides

**Impact :** L'arrêt d'urgence ne ferme pas les positions !

**Solution :** Implémenter les appels API Kraken réels

---

## 🟡 HAUTE - Important

### 4. Persistance d'état (SQLite)
**Problème :** Tout est en mémoire. Crash = perte de toutes les positions/trades

**Solution :** 
- Sauvegarder positions dans SQLite
- Restaurer au démarrage
- Logging des trades pour analytics

### 5. Tests d'intégration
- Tester avec API Kraken sandbox
- Tester scénarios : crash, reconnexion, annulation ordre

---

## 🟢 MOYENNE - Améliorations

### 6. Rate limiting API
- Protéger contre les abus sur `/api/emergency-stop`

### 7. Métriques Prometheus
- Exporter stats pour monitoring (Grafana)

### 8. Documentation utilisateur
- Guide "Premiers pas"
- FAQ dépannage

---

## 📋 Checklist avant déploiement

- [ ] SignalHandler connecte signaux aux exécutions
- [ ] `_get_available_capital()` appelle API Kraken
- [ ] `_close_all_positions_market()` implémenté
- [ ] Persistance SQLite des positions
- [ ] Tests avec vraies clés API (mode validate)
- [ ] Documentation à jour

**Estimation temps :** 2-3 jours de travail
