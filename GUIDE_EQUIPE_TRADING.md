# 🚀 GUIDE DÉMARRAGE ÉQUIPE TRADING

## ✅ Résumé de la configuration

### Équipe de 3 agents (optimisé sans GPT)

| Agent | Rôle | Modèle | Budget | Usage |
|-------|------|--------|--------|-------|
| **Kimi Dev** | Développement | `moonshot/kimi-k2.5` | 20€ | Génère code Python, tests, docs |
| **Gemini Review** | Review | `google/gemini-1.5-pro` | 20€ | Vérifie syntaxe, patterns, bugs |
| **Opus Security** | Audit + VETO | `anthropic/claude-3-opus` | 20$ | Sécurité, architecture, décision finale |

**Consensus :** 2/3 minimum + Opus APPROVED = déploiement

---

## 📁 Fichiers créés

```
/home/node/.openclaw/workspace/
├── trading-team.json           # Configuration équipe
├── docker-compose.trading.yml  # Docker Compose
├── trading-start.sh            # Démarrer l'équipe
├── trading-status.sh           # Voir le statut
└── trading-stop.sh             # Arrêter l'équipe
```

---

## 🎬 Démarrage

### 1. Prérequis

Avoir les clés API dans l'environnement :
```bash
export ANTHROPIC_API_KEY="ta_clé_anthropic"
export GOOGLE_API_KEY="ta_clé_google"  # Optionnel mais recommandé
```

### 2. Lancer l'équipe

```bash
cd C:\moltbot-projet\moltbot  # ou où sont tes fichiers
bash trading-start.sh
```

**Ou sous Windows (PowerShell avec WSL) :**
```powershell
wsl bash trading-start.sh
```

### 3. Vérifier que tout marche

```bash
bash trading-status.sh
```

---

## 🔍 Comment vérifier que les agents communiquent

### Test 1 : Event Bus (port 18789)

```bash
# Tester la connexion Redis
wsl docker exec trading-event-bus redis-cli ping
# Doit répondre : PONG
```

### Test 2 : Voir les canaux actifs

```bash
wsl docker exec trading-event-bus redis-cli PUBSUB CHANNELS
```

Doit afficher les canaux :
- `code.generated`
- `review.completed`
- `security.review`
- `consensus.conflict`
- `deploy.request`

### Test 3 : Envoyer un message test

```bash
wsl docker exec trading-event-bus redis-cli PUBLISH code.generated "Test message"
```

Les 3 agents doivent recevoir le message.

### Test 4 : Logs des agents

```bash
# Voir les logs Kimi
wsl docker logs kimi-developer --tail 20

# Voir les logs Gemini
wsl docker logs gemini-reviewer --tail 20

# Voir les logs Opus
wsl docker logs opus-security --tail 20
```

### Test 5 : Heartbeat (toutes les 5 min)

```bash
wsl docker logs heartbeat-monitor --tail 10
```

Doit montrer des pings réussis vers les 3 agents.

---

## 🔄 Workflow de développement

```
1. Tu demandes une feature
   ↓
2. Kimi Dev génère le code
   ↓ Publie sur canal "code.generated"
   ↓
3. Gemini + Opus analysent EN PARALLÈLE
   ↓ Publient sur "review.completed"
   ↓
4. Consensus automatique
   • Si 2/3 APPROVED + Opus APPROVED → Déploiement
   • Si conflit → Opus tranche (veto power)
   ↓
5. Code déployé dans /workspace/autobot/
```

---

## ⚠️ Règles de budget

| Agent | Règle si budget faible |
|-------|------------------------|
| Kimi | Continue (20€ = ~2000 requêtes) |
| Gemini | Continue (20€ = ~4000 requêtes) |
| **Opus** | **STOP si < 5$** → Alertes Telegram |

**Opus = critique** → Si épuisé, pause développement sécurité.

---

## 🛠️ Commandes utiles

```bash
# Voir tout
bash trading-status.sh

# Voir logs en direct
docker logs -f kimi-developer
docker logs -f gemini-reviewer
docker logs -f opus-security

# Redémarrer un agent
docker restart kimi-developer

# Arrêter tout
bash trading-stop.sh
```

---

## 🎯 Prochaine étape

1. **Tester le démarrage** : `bash trading-start.sh`
2. **Vérifier connexions** : `bash trading-status.sh`
3. **Première mission** : Demander à Kimi de générer un module Grid Trading

---

**Des questions ou tu veux lancer le test ?**
