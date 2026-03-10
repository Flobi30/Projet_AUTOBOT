# 🎨 TRACKING AJUSTEMENTS FRONTEND - AUTOBOT

## Frontend existant: "Nouveau Frontend AUTOBOT.zip"
## Status: À analyser et adapter

---

## 🔍 Analyse Initiale (À faire par Devin)

### Composants existants à identifier:
- [ ] Dashboard principal
- [ ] Affichage P&L (Profit & Loss)
- [ ] Graphiques temps réel
- [ ] Liste positions ouvertes
- [ ] Boutons actions (Start/Stop/Pause)
- [ ] Configuration/Paramètres
- [ ] Alertes/Notifications

### Adaptations nécessaires pour Grid Trading:
| Feature | Status | Action requise | Priorité |
|---------|--------|----------------|----------|
| Affichage niveaux Grid | 🔴 Non existant | Ajouter composant | HIGH |
| Visualisation grille (achats/ventes) | 🔴 Non existant | Créer vue grid | HIGH |
| Multi-instance (liste bots) | 🟡 À vérifier | Adapter si besoin | MEDIUM |
| Risk metrics (drawdown) | 🟡 À vérifier | Ajouter jauge risque | MEDIUM |
| Bouton "Nouvelle Instance" | 🔴 Non existant | Ajouter bouton + formulaire | LOW |

---

## 📝 Log des modifications (Mis à jour en temps réel)

### Itération 1 - Backend Core
**Date:** 2026-02-04 (Semaine 1)

**Backend livré:**
- ✅ API /api/instance/{id}/status
- ✅ API /api/instance/{id}/pnl
- ✅ Grid calculator opérationnel

**Modifs frontend identifiées:**
1. **Ajouter:** Composant `GridVisualizer` 
   - Afficher les 15 niveaux du grid
   - Couleur verte = niveau actif, gris = inactif
   - **Validation Flo:** Tu veux quel design ?

2. **Modifier:** Dashboard pour afficher:
   - Capital total vs engagé
   - Niveau grid actuel (prix actuel entre quel niveaux)
   - **Validation Flo:** Où placer cette info ?

3. **Ajouter:** Alertes visuelles:
   - Rouge si drawdown > 10%
   - Orange si daily loss > 25€
   - **Validation Flo:** Pop-up ou bannière ?

**Status:** ⏳ En attente GO de Flo pour modifs

---

### Itération 2 - Tests & Intégration
**Date:** À définir (Semaine 2)

**Modifs attendues:**
- Ajustements responsive (mobile/tablet)
- Couleurs P&L (vert/rouge plus visibles)
- Temps réel WebSocket (refresh auto)

---

## 🎨 Questions design pour Flo

### 1. Vue Grid
Tu préfères quel affichage pour les niveaux du grid ?

**Option A - Liste:**
```
Niveau 1: Buy 93,000€ → Sell 100,000€ [ACTIF]
Niveau 2: Buy 86,000€ → Sell 93,000€ [ACTIF]
Niveau 3: Buy 79,000€ → Sell 86,000€ [INACTIF]
```

**Option B - Visuel (type thermomètre):**
```
100K ┤▓▓▓ Sell  
 93K ┤▓▓▓ Buy   ← Prix actuel ici
 86K ┤░░░ Inactif
```

**Option C - Graphique:**
- Overlay sur le chart TradingView
- Lignes horizontales = niveaux grid

**Ta préférence ?** (A/B/C ou autre idée)

---

### 2. Multi-instance
Quand tu auras 2-3 bots, tu veux les voir comment ?

**Option A - Onglets:**
- [Instance 1 BTC] [Instance 2 ETH] [Instance 3 Forex]

**Option B - Dashboard global:**
- Vue d'ensemble tous les bots
- Clic pour détails d'un bot

**Option C - Split-screen:**
- 2-3 colonnes côte à côte (desktop uniquement)

**Ta préférence ?**

---

### 3. Alertes/Notifications
Comment tu veux être alerté ?

- 🔔 **Bannière dashboard** (dans l'interface)
- 📧 **Email** (si risque élevé)
- 💬 **Discord/Telegram** (webhook)
- 📱 **Push mobile** (si PWA)

**Quelle priorité ?**

---

## 🚀 Processus de validation

### Pour chaque modification frontend:

1. **Devin identifie** le besoin d'ajustement
2. **Kimi documente** ici avec options (A/B/C)
3. **Flo choisit** l'option ou propose alternative
4. **Devin implémente** la modif validée
5. **Claude review** le code frontend
6. **Kimi teste** l'intégration backend/frontend

### Timing:
- Questions design: **En amont** (avant codage)
- Ajustements mineurs: **En parallèle** (backend)
- Gros changements: **Itération suivante**

---

## ✅ Checklist Validation Frontend

Avant mise en production:

- [ ] Design validé par Flo
- [ ] Responsive (mobile/tablet/desktop)
- [ ] Couleurs accessibles (daltonisme)
- [ ] Temps réel fonctionnel (< 2s latence)
- [ ] Gestion erreurs (message si API down)
- [ ] Loading states (squelettes pendant chargement)
- [ ] Dark/Light mode (si pertinent)

---

**Dernière mise à jour:** 2026-02-04 16:58 UTC
**Prochaine update:** Quand Devin analyse le frontend existant