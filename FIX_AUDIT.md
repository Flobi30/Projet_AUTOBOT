## MISSION: Corrections Complètes — CRITIQUES + WARNINGS Audit AutoBot V2

### Contexte
Audit a trouvé 12 critiques et 24 warnings. Cette mission corrige les plus importants.

---

## 🔴 PRIORITÉ 1 — CRITIQUES (Bloquants Production)

### SEC-01 — Dashboard sans auth
**Fichier:** src/autobot/v2/api/dashboard.py
**Correction:** Token obligatoire si ENV != development

### SEC-03 — API keys en public  
**Fichier:** src/autobot/v2/order_executor_async.py
**Correction:** Utiliser SecretStr ou env vars

### BUG-01 — Division par zéro initial_capital=0
**Fichier:** src/autobot/v2/instance.py:565
**Correction:** Guard if initial_capital > 0 else 0.0

### CQ-04 — Validateur clés incompatibles
**Fichier:** src/autobot/v2/validator.py vs signal_handler.py
**Correction:** Aligner clés contexte

### CQ-05 — Grid sell ferme TOUTES les positions
**Fichier:** src/autobot/v2/signal_handler.py:168
**Correction:** Fermer seulement la position du level_index

### INF-01 — Dockerfile root user + pas de healthcheck
**Fichier:** Dockerfile
**Correction:** USER appuser + HEALTHCHECK

---

## 🟡 PRIORITÉ 2 — WARNINGS Importants

### ARC-03 — max_instances confusion sync/async
**Correction:** Guard dans main.py avec redirection

### ARC-04 — SPOF WebSocket unique
**Correction:** Fallback REST polling

### CQ-02 — Fonctions >100 lignes
**Correction:** Refactorer _close_all_positions_market

### CQ-06 — TrendStrategy 20% capital par trade
**Correction:** Utiliser RiskManager (2% risk)

### SEC-05 — .env pas dans .gitignore
**Correction:** Ajouter .env, data/, *.db

### INF-05 — Variables env non documentées
**Correction:** Mettre à jour .env.example

---

## Livrables
1. Tous les fichiers corrigés
2. Tests passant
3. Dockerfile mis à jour
4. .env.example complet
