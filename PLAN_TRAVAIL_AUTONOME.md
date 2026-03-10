# 🤖 PLAN DE TRAVAIL AUTONOME - AUTOBOT

## ⏱️ Cycle de travail (Prochaines 2-4 heures)

### Phase 1: Finalisation Data Connector (0-30 min)
**Agent:** Devin  
**Mission:** Compléter /src/data_connector/ + tests  
**Validation:** Claude review  
**Livrable:** PR GitHub prête

### Phase 2: Risk Manager (30-60 min)  
**Agent:** Devin (après validation Data Connector)  
**Mission:** Implémenter Risk Manager avec Kelly, VaR, Circuit Breakers  
**Specs:** /docs/ADR_RiskManager.md  
**Validation:** Kimi + Claude  

### Phase 3: Integration Tests (60-90 min)
**Agents:** Devin + Claude  
**Mission:** Tests end-to-end Data + Risk  
**Validation:** Kimi approval

### Phase 4: UI Scaffold (90-120 min)
**Agent:** Devin  
**Mission:** Structure React + composants base  
**Specs:** /docs/ADR_UI_React.md

---

## 🎯 Points de synchronisation (Checkpoints)

### Checkpoint 1 (Dans 20 min)
- [ ] Data Connector implémenté
- [ ] Tests >90%
- [ ] PR créée
- **Action:** Claude review → Kimi validation

### Checkpoint 2 (Dans 60 min)
- [ ] Risk Manager implémenté
- [ ] Integration tests pass
- **Action:** Validation architecture complète

### Checkpoint 3 (Dans 2h)
- [ ] UI React scaffold
- [ ] WebSocket connexion testée
- **Action:** Demo dashboard

---

## 🚨 STOP Conditions (Demander validation à Flo)

1. **Si ROI projeté < 25%** → Revoir stratégies
2. **Si latence > 200ms** → Optimisation requise  
3. **Si drawdown simulé > 20%** → Renforcer risk manager
4. **Si structure trop complexe** → Simplification
5. **Achat infrastructure > $100/mois** → Validation budget

---

## 📂 Documents créés (Prêts à l'emploi)

```
/home/node/.openclaw/workspace/docs/
├── ADR_DataConnector.md       ✅ (En cours implémentation)
├── ADR_RiskManager.md         ✅ (Phase 2 ready)
├── ADR_UI_React.md            ✅ (Phase 3 ready)
└── TEMPLATE_Impl_*.md         ✅ (Specs détaillées)

/home/node/.openclaw/workspace/
├── ROADMAP_AUTOBOT.html       ✅ (Vue d'ensemble)
├── CARTE_MENTALE_*.html       ✅ (Résumé visuel)
├── TRACKING_AUTOBOT.md        ✅ (Suivi temps réel)
└── LIVE_MONITOR.html          ✅ (Monitoring)
```

---

## 🎯 Objectif Final (Rappel)

**ROI Cible:** 30-40% mensuel  
**Max Drawdown:** <15%  
**UI:** React fluide, temps réel <100ms  
**Robustesse:** 99.9% uptime  

---

**Je travaille maintenant en autonomie avec Devin et Claude.**
**Je t'alerte aux checkpoints ou si STOP condition détectée.**

**Prochaine update:** Checkpoint 1 (dans ~20 min) ou sur événement critique.