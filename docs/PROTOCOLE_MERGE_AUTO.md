# 🔐 PROTOCOLE MERGE AUTOMATIQUE - AUTOBOT

## Règles de Merge (Validées par Flo)

### ✅ Devin peut merger SANS consultation si :
- [ ] **Coverage tests ≥ 90%** (minimum strict)
- [ ] CI/CD passe (tous checks verts)
- [ ] Pas de secrets/credentials en dur
- [ ] Review Claude completed (si assignée)
- [ ] **NON-CRITIQUE** : Refactoring, docs, tests, config

### ⚠️ Devin doit demander validation Kimi/Flo si :
- [ ] **Architecture changée** (structure modifiée)
- [ ] **Nouveau connecteur externe** (API, exchange)
- [ ] **Risk management modifié** (stop loss, sizing)
- [ ] **Dépenses** (infrastructure, services payants)
- [ ] **Security** (auth, encryption, clés API)
- [ ] **Coverage < 90%** mais merge nécessaire (exception)

### 🔴 MERGE INTERDIT (Stop immédiat) :
- [ ] Coverage < 80%
- [ ] Tests failed
- [ ] Secrets détectés
- [ ] Breaking changes sans doc

---

## 📋 Classification "Étapes Critiques"

### 🟢 NON-CRITIQUE (Devin merge auto si >90%)
- Refactoring code
- Ajout tests
- Documentation
- Bugfixes mineurs
- Configurations
- Frontend ajustements

### 🟡 MOYENNEMENT CRITIQUE (Notifier Kimi)
- Nouveau fichier core
- Modification API externe
- Performance changes
- Coverage 85-90%

### 🔴 CRITIQUE (Attendre GO Flo)
- **Phase 1 → Phase 2** (ex: Data → Grid)
- **Ajout instance** (nouveau bot avec capital)
- **Déploiement production** (Hetzner, live trading)
- **Risk params changés** (stop loss, max drawdown)
- **Connecteur financier** (Stripe, IB, exchange réel)
- **Capital réel > 1000€** impliqué

---

## 🚀 Workflow Merge Automatique

```
Devin code ──▶ Tests ──▶ Coverage?
                              │
                    ┌─────────┴─────────┐
                    ▼                   ▼
                ≥ 90%                < 90%
                    │                   │
            ┌───────┴───────┐          │
            ▼               ▼          │
        CRITIQUE?        Non-critique  │
            │               │          │
      ┌─────┴─────┐         │          │
      ▼           ▼         ▼          │
    OUI          NON     MERGE        │
      │           │       AUTO        │
      ▼           ▼         │          │
  Notifier     MERGE        │          │
  Kimi/Flo     AUTO         │          │
                              │          │
                              ▼          ▼
                          NOTIFY       BLOQUE
                          Kimi         Attend
                          (log)        amélioration
```

---

## 📊 Exemples concrets

| Situation | Coverage | Critique? | Action Devin |
|-----------|----------|-----------|--------------|
| Fix typo docs | N/A | Non | ✅ Merge auto |
| Ajout tests +5% | 92% | Non | ✅ Merge auto |
| Refactoring connector | 91% | Moyen | 🟡 Notifier Kimi |
| Nouveau Grid Engine | 95% | OUI (Phase 2) | 🔴 Attendre GO Flo |
| Config Hetzner | 90% | OUI (Déploiement) | 🔴 Attendre GO Flo |
| Bugfix rate limiter | 88% | Non | 🟡 Notifier Kimi (coverage <90) |
| Modif stop loss -15%→-20% | 95% | OUI (Risk) | 🔴 Attendre GO Flo |

---

## 🎯 Prochaines étapes autorisées

### ✅ Devin peut lancer MAINTENANT (sans attendre) :
1. **Phase 2 Grid Trading** - C'est une nouvelle phase critique
   - ⚠️ **ATTENTION :** Devin doit attendre GO Flo pour commencer
   
2. **Amélioration coverage** 87% → 90%
   - ✅ Devin peut merger auto quand ≥90%

3. **Setup CI/CD** (si pas fait)
   - ✅ Non-critique, merge auto

### 🔴 Doit attendre GO Flo :
1. **Déploiement Hetzner** (serveur + capital réel)
2. **Premier trade live** (même 1€)
3. **Ajout Instance #2** (ETH avec nouveau capital)

---

## 📝 Log des merges autonomes

| Date | PR | Coverage | Critique? | Action | Par |
|------|-----|----------|-----------|--------|-----|
| 2026-02-04 | #39 | 87% | OUI (Architecture) | 🔴 Attend Flo | - |
| - | - | - | - | - | - |

**Dernière update:** 2026-02-04 19:55 UTC

---

## ✅ Validation

**Flo a approuvé ce protocole :**
- ✅ Merge auto si coverage ≥ 90% ET non-critique
- ✅ Consultation requise pour étapes critiques
- 🔐 Sécurité : Jamais merge si secrets ou tests failed

**Implémenté par:** Kimi (Architecte)