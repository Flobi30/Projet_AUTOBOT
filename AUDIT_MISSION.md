## MISSION: AUDIT COMPLET AutoBot V2 — Infrastructure, Bugs, Erreurs

Tu es auditeur senior. Fais un audit exhaustif de tout le projet.

### Scope
- /home/node/.openclaw/workspace/src/autobot/v2/ (tout)
- Architecture P0-P6
- 19 modules de performance
- 4 stratégies
- Infrastructure (Docker, config, déploiement)

### Checklist Audit

#### 1. Architecture & Design
- [ ] Cohérence architecture P0-P6
- [ ] Points de défaillance single point of failure
- [ ] Scalabilité réelle (2000 instances)
- [ ] Latence P99 vs objectifs

#### 2. Code Quality
- [ ] Code duplications
- [ ] Complexité cyclomatique
- [ ] Fonctions trop longues (>50 lignes)
- [ ] Classes trop grosses (>500 lignes)
- [ ] Dépassements de listes/arrays

#### 3. Sécurité
- [ ] Injection SQL (SQLite)
- [ ] Fuite de données sensibles (logs, erreurs)
- [ ] Validation entrées utilisateur
- [ ] Secrets en dur
- [ ] Race conditions restantes

#### 4. Infrastructure
- [ ] Docker config (ports, volumes, réseau)
- [ ] Variables d'environnement manquantes
- [ ] Health checks
- [ ] Monitoring/alerting
- [ ] Backup/recovery

#### 5. Bugs Potentiels
- [ ] Off-by-one errors
- [ ] Division par zéro non gérée
- [ ] Null/None non vérifié
- [ ] Boucles infinies possibles
- [ ] Fuite mémoire (collections qui croissent)

#### 6. Tests
- [ ] Couverture de code (<80% ?)
- [ ] Tests d'intégration manquants
- [ ] Tests E2E manquants
- [ ] Tests de charge

#### 7. Documentation
- [ ] Docstrings manquantes
- [ ] README à jour
- [ ] Architecture diagrams
- [ ] Runbooks ops

### Format de rapport
Pour chaque problème trouvé:
- 🔴 CRITIQUE (bloquant production)
- 🟡 WARNING (risque élevé)
- 🟢 INFO (amélioration)

Structure:
```
## [CATEGORIE]
### 🔴 [ID] — [Titre]
**Fichier:** `path/to/file.py:line`
**Problème:** [Description]
**Impact:** [Conséquence]
**Recommandation:** [Solution]
```

### Livrables
1. Rapport audit complet (AUDIT_COMPLET.md)
2. Liste priorisée des problèmes
3. Plan d'action recommandé
