# CONFIGURATION_APIS.md - Accès APIs et Outils

**Date création:** 2026-02-06  
**Dernière mise à jour:** 2026-02-06  
**Status:** ✅ Vérifié et fonctionnel

---

## ⚠️ LEÇON APRISE (2026-02-06)

**Problème:** Confusion sur mes capacités d'accès aux APIs  
**Impact:** Perturbation inutile de Flo, perte de temps  
**Solution:** Ce fichier de référence obligatoire

---

## 🔑 CLÉS API CONFIGURÉES (ENVIRONNEMENT)

Toutes ces clés sont présentes dans l'environnement Docker:

| Variable | Status | Utilisation |
|----------|--------|-------------|
| `DEVIN_API_KEY` | ✅ **ACTIF** | Envoyer messages à Devin, créer sessions |
| `ANTHROPIC_API_KEY` | ✅ **ACTIF** | Utiliser Claude pour review |
| `CLAUDE_AI_SESSION_KEY` | ✅ **ACTIF** | Sessions Claude |
| `CLAUDE_WEB_COOKIE` | ✅ **ACTIF** | Accès web Claude |
| `CLAUDE_WEB_SESSION_KEY` | ✅ **ACTIF** | Sessions web Claude |

**Commande de vérification:**
```bash
env | grep -E "(DEVIN|ANTHROPIC|CLAUDE)" | sed 's/=.*/=***/'
```

---

## 🤖 CE QUE JE PEUX FAIRE AVEC DEVIN

### ✅ Automatique (sans intervention Flo)

1. **Vérifier statut session**
   ```bash
   curl -H "Authorization: Bearer $DEVIN_API_KEY" \
        "https://api.devin.ai/v1/session/{SESSION_ID}"
   ```

2. **Envoyer un message à une session active**
   ```bash
   curl -X POST "https://api.devin.ai/v1/session/{SESSION_ID}/message" \
        -H "Authorization: Bearer $DEVIN_API_KEY" \
        -H "Content-Type: application/json" \
        -d '{"message": "..."}'
   ```

3. **Créer une nouvelle session**
   ```bash
   curl -X POST "https://api.devin.ai/v1/sessions" \
        -H "Authorization: Bearer $DEVIN_API_KEY" \
        -H "Content-Type: application/json" \
        -d '{"prompt": "..."}'
   ```

### ❌ Impossible (limitation Devin)

- Voir le solde ACU depuis l'intérieur d'une session
- Devin doit donner cette info lui-même ou aller sur https://app.devin.ai/settings/usage

---

## 🔍 CE QUE JE PEUX FAIRE AVEC CLAUDE (ANTHROPIC)

- ✅ Review de code via API
- ✅ Analyse de PR
- ✅ Tests automatisés

---

## 📝 WORKFLOW STANDARD DEVIN

### Pour demander quelque chose à Devin:

1. **J'envoie directement** via API (pas besoin de Flo)
2. **Je récupère la réponse** via polling API
3. **Je rapporte à Flo** sur Telegram

### Exemple - Demander solde ACU:

```bash
# Créer session pour poser la question
curl -X POST "https://api.devin.ai/v1/sessions" \
  -H "Authorization: Bearer $DEVIN_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Question: Combien d'ACUs reste-t-il sur ce compte? Réponse courte."
  }'

# Vérifier réponse après 10-30 secondes
curl -H "Authorization: Bearer $DEVIN_API_KEY" \
     "https://api.devin.ai/v1/session/{NEW_SESSION_ID}"
```

---

## ❌ ERREURS À NE PLUS JAMAIS FAIRE

1. **Dire "je ne peux pas"** sans vérifier les variables d'environnement
2. **Demander à Flo de faire ce que je peux faire** via API
3. **Être incohérent** entre Telegram et OpenClaw web (c'est le même agent!)

### Procédure obligatoire:
- [ ] Avant de dire "je ne peux pas", vérifier `env | grep API`
- [ ] Si la clé existe, tester la commande curl
- [ ] Si ça marche, l'utiliser directement
- [ ] Si ça ne marche pas, alors demander à Flo

---

## 🔄 SYNCHRONISATION TELEGRAM ↔ OPENCLAW

**FAIT:** C'est le même agent avec les mêmes outils
- Mêmes variables d'environnement
- Mêmes fichiers memory
- Mêmes capacités API

**ATTENTION:** Je ne vois pas l'historique complet des conversations passées
- Toujours lire les fichiers `memory/YYYY-MM-DD.md` pour le contexte
- Ne pas présumer de mémoire des conversations non sauvegardées

---

## 📂 FICHIERS DE RÉFÉRENCE OBLIGATOIRES

Avant de répondre sur les capacités, vérifier:
1. `/home/node/.openclaw/workspace/memory/YYYY-MM-DD.md` (aujourd'hui + hier)
2. `/home/node/.openclaw/workspace/MEMORY.md` (mémoire long terme)
3. **CE FICHIER** (`CONFIGURATION_APIS.md`)

---

## 🎯 RÈGLE D'OR

> **Si la clé API existe dans l'environnement, je DOIS l'utiliser.**
> 
> **Ne jamais dire "je ne peux pas" sans vérifier d'abord.**

---

**Dernière vérification:** 2026-02-06 19:58 UTC  
**Prochaine revue:** À chaque doute sur les capacités
