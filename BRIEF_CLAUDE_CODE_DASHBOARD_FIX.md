# 🎯 Brief Claude Code — Corrections Dashboard AUTOBOT

**Date:** 2026-04-07  
**Priorité:** HIGH  
**Repo:** `github.com/Flobi30/Projet_AUTOBOT`  
**Branch:** `main`  

---

## Contexte

Le dashboard React (dans `dashboard/src/`) a plusieurs bugs qui empêchent son bon fonctionnement. Le backend FastAPI (`src/autobot/v2/api/dashboard.py`) fonctionne correctement. Il faut corriger le frontend.

Le serveur de production est à `204.168.205.73`, le projet est dans `/opt/Projet_AUTOBOT`.

---

## Bugs à corriger

### 1. 🔴 URLs hardcodées HTTP → URLs relatives
**Fichiers concernés :** TOUS les `.tsx` dans `dashboard/src/pages/`
- `Performance.tsx`, `Capital.tsx`, `Diagnostic.tsx`, `Analytics.tsx`, `Backtest.tsx`, `LiveTrading.tsx`

**Problème :** Chaque fichier contient :
```tsx
const API_BASE_URL = 'http://204.168.205.73:8080';
```
Le serveur tourne en **HTTPS**. Le navigateur bloque les appels mixed content (HTTP vers une page HTTPS).

**Fix :** Remplacer par une URL relative dans TOUS les fichiers :
```tsx
const API_BASE_URL = '';
```
Le frontend est servi par le même serveur FastAPI, donc les URLs relatives (`/api/status`, `/api/capital`, etc.) fonctionnent directement.

---

### 2. 🔴 Auth manquante sur Capital.tsx et Analytics.tsx
**Fichiers :** `Capital.tsx`, `Analytics.tsx`

**Problème :** Ces fichiers font des `fetch()` sans header `Authorization`. Le backend exige un Bearer token en production → erreur 401/403.

**Fix :** Ajouter dans chaque fichier :
```tsx
const API_TOKEN = 'autobot_token_12345';
```
Et ajouter le header sur CHAQUE appel fetch :
```tsx
headers: { 'Authorization': `Bearer ${API_TOKEN}` }
```

Vérifier que c'est fait pour TOUS les fetch dans :
- `Capital.tsx` : `/api/capital`, `/api/status`, `/api/trades`
- `Analytics.tsx` : `/api/capital`, `/api/history`

Les autres fichiers (`Performance.tsx`, `Diagnostic.tsx`, `LiveTrading.tsx`, `Backtest.tsx`) ont déjà le token — vérifier quand même.

---

### 3. 🔴 Encodage Unicode — caractères échappés au lieu d'UTF-8
**Fichiers concernés :** Principalement `Performance.tsx`, potentiellement d'autres

**Problème :** Les caractères français sont écrits en escapes Unicode au lieu d'UTF-8 :
```
\u00e9 → devrait être é
\u00e8 → devrait être è
\u00c9 → devrait être É
\u00ee → devrait être î
\u00e0 → devrait être à
\u00e7 → devrait être ç
\u00f4 → devrait être ô
```

Résultat visible sur le dashboard : "Vue consolid\u00e9e des performances" au lieu de "Vue consolidée des performances"

Les emojis aussi sont en surrogate pairs :
```
\ud83d\udcca → 📊
\ud83d\udcc9 → 📉
\ud83d\udcb0 → 💰
\u26a0\ufe0f → ⚠️
\u2696\ufe0f → ⚖️
\u2014 → —
\u25bc → ▼
\u20ac → €
```

**Fix :** Remplacer TOUTES les séquences `\uXXXX` par les vrais caractères UTF-8 dans tous les fichiers `.tsx`.

Commande de vérification : `grep -rn '\\u00' dashboard/src/pages/` ne doit rien retourner après fix.

---

### 4. 🟡 Page Performance — Pas d'indicateur Paper Trading ni d'activité bot
**Fichier :** `Performance.tsx`

**Problème :** La page ne montre pas que le bot est en mode paper trading, ni qu'il est actif et connecté à Kraken. L'utilisateur ne sait pas si le bot s'entraîne réellement.

**Fix :** Ajouter deux éléments visuels en haut de la page (après le titre, avant les tabs) :

**A) Bandeau Paper Trading :**
- Appeler `/api/paper-trading/summary` (déjà appelé dans `fetchAll`)
- Si `is_paper_mode === true` : afficher un bandeau amber/orange :
  - Icône 🎓 + "Mode Entraînement (Paper Trading)"
  - "Le bot s'entraîne avec du capital virtuel. Aucun argent réel n'est engagé."
  - "Capital réel : 0,00 €" / "Capital paper : {capital_total} €"
- Si `is_paper_mode === false` : bandeau vert "Mode Live Trading"

**B) Statut Bot en temps réel :**
- Appeler `/api/status` (ajouter au fetchAll)
- Afficher :
  - Point vert animé (pulse) si `websocket_connected === true`
  - "Bot Actif — Données Kraken Live" ou "Bot Déconnecté"
  - WebSocket : ✅ Connecté / ❌ Déconnecté
  - Instances : {instance_count} active(s)
  - Uptime : {heures}h {minutes}m
  - Trades : {total_trades} exécutés

Le `PaperSummary` interface a déjà `is_paper_mode` dans la réponse API mais ce champ n'existe pas dans l'interface TypeScript actuelle. L'interface a `pairs_tested: string[]` mais l'API retourne `pairs_tested: number`. Corriger l'interface aussi.

---

### 5. 🟡 Page Capital — Distinguer Paper vs Réel
**Fichier :** `Capital.tsx`

**Problème :** Affiche "Capital Total: 1 000 €" même en paper trading. L'utilisateur pense que c'est son argent réel.

**Fix :**
- Appeler `/api/paper-trading/summary` pour savoir si on est en paper mode
- Si paper mode :
  - Changer le titre "Capital Total" → "Capital Paper (virtuel)"
  - Ajouter un bandeau amber : "🎓 Mode Paper Trading actif — Les montants affichés sont virtuels (entraînement)"
- Si live mode : garder le comportement actuel

---

### 6. 🟡 Dockerfile healthcheck HTTP → HTTPS
**Fichier :** `Dockerfile` (racine du projet)

**Problème :** La ligne healthcheck utilise HTTP :
```dockerfile
CMD curl -f http://localhost:8080/health || exit 1
```

**Fix :**
```dockerfile
CMD curl -fk https://localhost:8080/health || exit 1
```
(`-k` car le cert est auto-signé)

---

### 7. 🟡 docker-compose.yml — Binding port
**Fichier :** `docker-compose.yml`

**Situation actuelle :**
```yaml
ports:
  - "127.0.0.1:8080:8080"
```

**Fix :** Changer pour permettre l'accès externe (protégé par HTTPS + token auth) :
```yaml
ports:
  - "0.0.0.0:8080:8080"
```

---

## Workflow de déploiement

Après avoir fait toutes les corrections :

```bash
# 1. Commit et push sur GitHub
git add -A
git commit -m "fix: dashboard — encoding UTF-8, URLs relatives, auth headers, indicateurs paper trading"
git push origin main

# 2. Sur le serveur (204.168.205.73)
ssh root@204.168.205.73
cd /opt/Projet_AUTOBOT
git pull origin main
docker-compose down
docker-compose up -d --build

# 3. Vérification
curl -sk https://localhost:8080/health
curl -sk https://204.168.205.73:8080/api/status -H 'Authorization: Bearer autobot_token_12345'
```

---

## Vérifications post-déploiement

- [ ] `https://204.168.205.73:8080` charge le dashboard sans erreur
- [ ] Page Performance : texte en français correct (pas de `\u00e9`)
- [ ] Page Performance : bandeau "Mode Entraînement (Paper Trading)" visible
- [ ] Page Performance : statut bot avec WebSocket connecté, uptime affiché
- [ ] Page Capital : titre "Capital Paper (virtuel)" + bandeau paper
- [ ] Page Diagnostic : pas de "fails to fetch"
- [ ] Console navigateur (F12) : aucune erreur CORS ou mixed content
- [ ] `docker inspect autobot-v2 --format='{{.State.Health.Status}}'` → healthy

---

## Fichiers modifiés (résumé)

| Fichier | Changements |
|---------|------------|
| `dashboard/src/pages/Performance.tsx` | URL relative, encodage UTF-8, bandeau paper + statut bot |
| `dashboard/src/pages/Capital.tsx` | URL relative, auth headers, distinction paper/réel |
| `dashboard/src/pages/Diagnostic.tsx` | URL relative, encodage UTF-8 |
| `dashboard/src/pages/Analytics.tsx` | URL relative, auth headers |
| `dashboard/src/pages/Backtest.tsx` | URL relative, encodage UTF-8 |
| `dashboard/src/pages/LiveTrading.tsx` | URL relative, encodage UTF-8 |
| `Dockerfile` | Healthcheck HTTP → HTTPS |
| `docker-compose.yml` | Binding `0.0.0.0:8080` |

---

*Brief rédigé par Opus — à transmettre à Claude Code pour implémentation.*
