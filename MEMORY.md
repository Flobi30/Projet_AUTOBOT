# MEMORY.md - Mémoire long terme

## ⚠️ RÈGLES CRITIQUES (à lire avant toute action)

### 🔑 Configuration APIs - FICHIER OBLIGATOIRE
**Avant de dire "je ne peux pas", LIRE :**
📄 `/home/node/.openclaw/workspace/CONFIGURATION_APIS.md`

**Ce fichier contient:**
- Toutes les clés API disponibles (Devin, Claude, etc.)
- Commandes exactes pour interagir avec Devin
- Procédures workflow standard
- **LEÇONS DES ERREURS PASSÉES**

### ❌ Erreur du 2026-02-06 (à ne plus jamais reproduire)
**Problème:** Confusion sur mes capacités API, réponses contradictoires
**Cause:** N'avoir pas vérifié les variables d'environnement avant de parler
**Solution:** Toujours lire CONFIGURATION_APIS.md avant toute réponse sur les capacités

---

## 🤖 HABITUDE DE TRAVAIL AVEC DEVIN (2026-02-06)

### ✅ RÈGLE OBLIGATOIRE POUR CHAQUE SESSION DEVIN

**Depuis le 2026-02-06, cette règle est STRICTE :**

> **Chaque PR doit inclure des tests automatisés qui valident les aspects fonctionnels.**
> 
> **INTERDIT de demander à l'humain de "vérifier manuellement" ou "tester".**

**Pourquoi ?**
- Les checks CI/CD valident le code technique, pas la qualité fonctionnelle
- Devin demandait "vérifiez que le message est acceptable" → erreurs passaient quand même
- Solution : TOUT doit être testé automatiquement par la CI/CD

### 📋 À inclure dans CHAQUE prompt Devin :

```markdown
## RÈGLE CRITIQUE - TESTS AUTOMATIQUES
- Ne demande JAMAIS à l'humain de "vérifier" ou "tester" manuellement
- Chaque fonctionnalité doit avoir son test automatique
- Si tu écris un message d'erreur → teste-le
- Si tu crées une fonction → teste-la
```

### 📁 Fichier de référence :
📄 `/home/node/.openclaw/workspace/PROTOCOLE_DEVIN.md`

**Mémoriser :** "La confiance n'exclut pas le contrôle" → mais le contrôle doit être automatique (CI/CD), pas manuel.

---

## À propos de Flo (Florent)
- Porteur du projet **AUTOBOT** - robot de trading algorithmique crypto/forex
- Non-développeur mais vision claire du projet
- A déjà travaillé avec Devin AI (Cognition) et Claude
- **ID Telegram :** 5839618544
- **Exigence :** Système qui MARCHE vraiment, pas du scaffold
- **Vision :** Court terme (résultats rapides) + Long terme (évolutif)
- **Situation :** Budget très serré (peu de revenus)

## Projet AUTOBOT - VISION CLARIFIÉE (2026-02-05)

### Court terme (Stratégie initiale)
- **Objectif :** 15-20% mensuel
- **Capital :** 500€ (montant alloué au trading uniquement)
- **Instance :** 1 seule (pour commencer)
- **Marché :** Crypto (priorité) ou Forex
- **Effort :** Minimal (système autonome)
- **Stratégie :** Grid Trading statique (simple, prévisible)

### Scalabilité rapide (Intérêts composés)
- Réinvestissement automatique des gains
- Multiplication des instances (même stratégie, marchés différents)
- Évolution possible vers :
  - Levier (x2, x3 selon confiance)
  - HFT (si hardware suffisant)
  - Multi-stratégies (adaptation marché)

### Performance
- **Mixte :** Modéré-agressif
- **Adaptatif :** Selon trésorerie disponible
- **Scalable :** Croissance avec les gains

### Long terme
- Revenus passifs significatifs
- Peu de maintenance requise
- Marge de manoeuvre financière confortable

### Contraintes
- **Budget dev :** Minimum possible (situation financière serrée)
- **Risque max :** 20% drawdown
- **Autonomie :** 100% (pas de surveillance quotidienne)

## Configuration système
- Recherche web Brave activée (février 2026)
- Container Docker OpenClaw
- **Workspace :** C:\openclaw\ (Windows + WSL2)

## Collaboration inter-agents
- **Kimi** (OpenClaw) → Orchestrateur principal, architecture, coordination
- **Devin** (Cognition) → Développement
- **Claude** (Anthropic) → Review code
- Format de communication : **KERNEL**

### Format KERNEL (prompts structurés)
| Lettre | Principe | Description |
|--------|----------|-------------|
| **K** | Keep it simple | Un seul objectif clair, pas de blabla |
| **E** | Easy to verify | Critères de succès mesurables |
| **R** | Reproducible results | Pas de références temporelles |
| **N** | Narrow scope | Un prompt = une tâche |
| **E** | Explicit constraints | Dire ce qu'il NE faut PAS faire |
| **L** | Logical structure | Contexte → Tâche → Contraintes → Format |

## Phases de développement (Budget serré)

### Phase 1 : MVP Grid (Minimal Viable Product)
**Objectif :** 1 bot qui marche, 500€, 15%/mois
**Budget :** ~200-300€ (Devin optimisé)
**Durée :** 3-4 semaines
**Livrable :** Bot Grid fonctionnel sur Kraken (pas Binance - problème géoblocage) puis live

### Phase 2 : Optimisation
**Objectif :** Passer à 20%/mois, ajouter 1-2 stratégies simples
**Budget :** ~100-200€ (améliorations ciblées)
**Durée :** 2-3 semaines
**Livrable :** Multi-stratégies basiques

### Phase 3 : Scaling
**Objectif :** Multi-instance, réinvestissement auto
**Budget :** ~100€ (automatisation)
**Durée :** 2 semaines
**Livrable :** Orchestration multi-bots

**TOTAL BUDGET DEV :** 400-600€ max

## Exchange choisi
**Plateforme :** Kraken (https://www.kraken.com/)
**Pourquoi Kraken et pas Binance :**
- ✅ Pas de géoblocage (serveurs Devin fonctionnent)
- ✅ API stable et bien documentée
- ✅ Pas de restriction géographique stricte
- ⚠️ Frais: 0.16% maker / 0.26% taker (vs 0.1% Binance)
- 📝 Adaptation code nécessaire (symboles: XXBTZEUR, pas BTCUSDT)

**Librairie Python :** krakenex ou ccxt (pas python-binance)

## Points d'attention
- ⚠️ Budget très serré → Pas de fonctionnalités inutiles
- ⚠️ Priorité : Fonctionner > Architecture parfaite > Features
- ⚠️ Scalabilité progressive (avec les gains, pas avec le budget dev)
- ⚠️ Kimi doit challenger les coûts et proposer alternatives économiques
- ⚠️ Flo n'est pas développeur ni trader → Explications simples, pas de jargon

## Configuration Telegram (Alertes)
- **Bot :** @Autotobot_Clawbot
- **Token :** 8276786695:AAE1VczGWvAL6OZUdr8AXmX3rmep_C_ajRU
- **Chat ID :** 5839618544
- **Status :** ✅ Actif
- **Cron :** Toutes les 10 minutes (à vérifier - problème technique)

## APIs Configurées
- ✅ **Devin API** → Envoi de prompts à Devin AI
- ✅ **Anthropic API** → Review par Claude
- ✅ **Telegram Bot API** → Alertes utilisateur

## Fichiers importants
- `/home/node/.openclaw/workspace/docs/BRIEF_AUTOBOT_v1.md` - Brief complet
- `/home/node/.openclaw/workspace/autobot/` - Code source (À REFONDRE)
- `/home/node/.openclaw/workspace/PROTOCOLE_SAUVEGARDE.md` - Sauvegarde auto
- `/home/node/.openclaw/workspace/AUDIT_GITHUB_AUTOBOT.md` - Audit des problèmes
- `/home/node/.openclaw/workspace/MODE_EMPLOI_KIMI.md` - Mon rôle défini
- `/home/node/.openclaw/workspace/tests/test_grid_integration.py` - Tests créés par Claude

## Sauvegarde automatique
- **Activée :** Oui
- **Fréquence :** Toutes les 6 heures + événements majeurs
- **Fichiers :** MEMORY.md + memory/YYYY-MM-DD.md + PROTOCOLE_SAUVEGARDE.md

## Bilan journée 2026-02-05 (Session intensive)
**Résultat :** 6 tâches sur 7 terminées (85% de la Phase 1)
- ✅ Connexion Kraken API
- ✅ Prix temps réel
- ✅ Grid Calculator (15 niveaux)
- ✅ Order Manager
- ✅ Position Manager (BUY→SELL)
- ✅ Gestion erreurs robuste
- 🔄 Tests intégration (en cours)

**Livrables :** 7 PR mergées, architecture Grid Trading complète
**Budget ACUs :** ~20 utilisés pour 6 tâches (efficace)
**Prochaine étape :** Tests finaux + audit + déploiement

## Instructions de fonctionnement (de Flo)

### Autonomie de décision
- **PR avec >90% coverage** → Kimi/Devin peut merger automatiquement
- **Étape critique** → Consulter Flo obligatoirement avant action
- **Avancement normal** → Informer Flo via Telegram sans attendre sa demande

### Communication
- **Telegram** : Canal prioritaire pour les alertes
- **Fréquence** : Alertes sur événements majeurs uniquement
- **Pas de spam** : Pas de message pour avancement mineur

### Monitoring
- **Cron** : Vérification toutes les 10 minutes (problème technique identifié)
- **Vérification** : Kimi vérifie lui-même, pas besoin de demander à Flo
- **Proactivité** : Alerter Flo automatiquement si problème ou avancée importante

### 🔍 NOUVEAU : Audit rigoureux à chaque PR (2026-02-06)
**Depuis l'erreur d'évaluation du 05/02, procédure stricte :**
- **TOUJOURS** vérifier les imports avant de dire "ça marche"
- **TOUJOURS** tester l'exécution réelle (`python -c "import..."`)
- **TOUJOURS** vérifier l'intégration (le code est-il appelé ?)
- **JAMAIS** merger sans rapport d'audit complet
- **Template:** `/home/node/.openclaw/workspace/PROCEDURE_AUDIT.md`

## Prochaines étapes
- [x] Valider plan Phase 1 (MVP Grid) avec Flo
- [x] Estimation précise coût Devin pour Phase 1
- [x] Définir critères "fonctionnel" (démonstration obligatoire)
- [x] Lancer reconstruction propre avec TDD
- [x] Tâches 1-6 terminées (2026-02-05)
- [ ] Attendre Tâche 7 (tests finaux)
- [ ] Audit complet par Kimi
- [ ] Frontend React (si nécessaire)
- [ ] Déploiement serveur dédié
- [ ] Tests live avec capital réel
