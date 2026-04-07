# 🔍 REVIEW OPUS & GEMINI - Corrections AUTOBOT V2

**Date:** 2026-04-06  
**Commits à reviewer:** `6ab3f6a4` → `645ca195`  
**Scope:** Dashboard Capital, Grid Strategy, Nouveaux endpoints API

---

## 📁 FICHIERS MODIFIÉS

### 1. dashboard/src/pages/Capital.tsx
**Changements:**
- ❌ Suppression des valeurs hardcodées ("5,420€", "1,285€")
- ✅ Ajout de `useEffect` avec fetch toutes les 5s vers `/api/capital`
- ✅ Fallback vers `/api/status` si `/api/capital` indisponible
- ✅ Connexion au store Zustand (`setCapitalTotal`)
- ✅ Récupération des trades via `/api/trades?limit=10`
- ⚠️ **RESTE À FAIRE:** Boutons dépôt/retrait pointent encore vers Stripe (doit être Kraken)

**Points de review:**
- [ ] Le fallback `/api/status` est-il robuste ?
- [ ] Le polling 5s est-il optimal ou faut-il du WebSocket ?
- [ ] Gestion des erreurs suffisante ?
- [ ] Stripe est encore là (lignes 8, 16, 98-124) → doit être supprimé

---

### 2. src/autobot/v2/api/dashboard.py
**Changements:**
- ✅ Ajout endpoint `GET /api/capital` avec calculs (total, profit, investi, disponible)
- ✅ Ajout endpoint `GET /api/trades?limit=50` avec pagination
- ✅ Protection division par zéro dans `/api/trades`

**Points de review:**
- [ ] Calcul `available_cash = total_capital * 0.1` → logique métier correcte ?
- [ ] Les endpoints sont-ils cohérents avec le reste de l'API ?
- [ ] Asynchronicité correcte ? (`async def` partout)

---

### 3. src/autobot/v2/strategies/grid_async.py
**Changements:**
- ✅ `center_price` passe de `50000.0` à `None` par défaut
- ✅ Ajout `self._grid_initialized = False`
- ✅ Initialisation dynamique au premier prix dans `on_price()`
- ✅ DGT initialisé aussi au premier prix

**Points de review:**
- [ ] Que se passe-t-il si le premier prix est aberrant (flash crash) ?
- [ ] Le recentering DGT fonctionne-t-il toujours avec ce changement ?
- [ ] Les niveaux sont-ils correctement recalculés si le prix dérive >20% ?
- [ ] `_emergency_close_price` protégé contre `center_price=None` ?

---

### 4. src/autobot/v2/risk_manager.py
**Changements:**
- ✅ `circuit_breaker_pf_low()` → `async def` + `await`
- ✅ `_check_risk_limits()` → `async def` + `await`
- ✅ `check_global_risk()` → `async def` + `await`

**Points de review:**
- [ ] Tous les appelants sont-ils maintenant `await` ?
- [ ] Pas de régression sur le circuit breaker ?
- [ ] Gestion du cas PF=0.0 toujours présente ?

---

## 🎯 QUESTIONS CLÉS POUR LES REVIEWERS

### Pour Opus (focus sécurité/architecture)
1. L'initialisation dynamique de la grid au premier prix est-elle safe ?
2. Le fallback `/api/status` dans Capital.tsx crée-il une dépendance cachée ?
3. Les endpoints `/api/capital` et `/api/trades` exposent-ils trop d'infos ?

### Pour Gemini (focus performance/optimisation)
1. Le polling 5s sur Capital.tsx est-il efficace ? WebSocket préférable ?
2. Le calcul des trades dans `/api/trades` est-il optimisé ?
3. L'initialisation lazy de la grid impacte-t-elle la latence du premier trade ?

---

## ⚠️ PROBLÈMES CONNUS RESTANTS

| Problème | Fichier | Sévérité |
|----------|---------|----------|
| Stripe encore importé/utilisé | Capital.tsx | 🟡 Moyen |
| Boutons dépôt/retrait non fonctionnels | Capital.tsx | 🟡 Moyen |
| Graphique LiveTrading toujours mock | LiveTrading.tsx | 🟢 Faible |
| Pas de vraie persistance historique | dashboard.py | 🟢 Faible |

---

## ✅ CRITÈRES D'APPROBATION

**SAFE_FOR_TESTING si:**
- [ ] Pas d'erreur de syntaxe TypeScript/Python
- [ ] Grid s'initialise correctement au premier prix
- [ ] Capital affiche les vraies données de l'API
- [ ] Endpoints `/api/capital` et `/api/trades` répondent 200

**NEEDS_FIX si:**
- [ ] Stripe doit être complètement supprimé
- [ ] Boutons doivent rediriger vers Kraken
- [ ] Gestion d'erreur insuffisante

---

*Document généré pour review par Opus & Gemini*