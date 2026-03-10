# 🔒 PROTOCOLE MERGE - AUTOBOT

## Règle d'Or
**AUCUN MERGE** sans les 4 validations :
1. ✅ Devin (Code + Tests)
2. ✅ Claude (Review qualité)
3. ✅ Kimi (Validation architecture)
4. ✅ Flo (Permission finale)

## Workflow

```
Devin code ──▶ Tests locaux ──▶ PR Draft
                                      │
                                      ▼
                           Claude Review (15 points)
                                      │
                                      ▼
                           Kimi Validation archi
                                      │
                                      ▼
                           Flo Decision (GO/NO-GO)
                                      │
                         ┌────────────┴────────────┐
                         ▼                         ▼
                       MERGE                    REFACTOR
                         │                         │
                         ▼                         ▼
                    CI/CD Run               Back to Devin
                         │
                         ▼
                   Deploy Ready
```

## CI/CD Requirements

Avant merge, doit passer :
- [ ] Tests unitaires >90%
- [ ] Lint (flake8/black)
- [ ] Type check (mypy)
- [ ] Security scan (bandit)
- [ ] Coverage report

## Checklist Validation (Pour Flo)

### Avant de dire "GO" :
- [ ] Architecture respectée (ADR)
- [ ] Pas de breaking changes
- [ ] Tests suffisants
- [ ] Documentation à jour
- [ ] Performance acceptable
- [ ] Pas de dette technique majeure

### Si "NO-GO" :
- Expliciter les changements demandés
- Réassigner à Devin
- Nouveau cycle review

## Tâches Parallèles Autorisées

SANS merge, on peut faire :
1. ✅ Préparation prochaines phases
2. ✅ Documentation
3. ✅ Tests unitaires isolés
4. ✅ Configuration CI/CD
5. ✅ Review code préparatoire

## Tâches Bloquées (Attendre merge)

- 🔴 Intégration modules entre eux
- 🔴 Tests E2E complets
- 🔴 Déploiement production
- 🔴 Connexions externes (IB, Stripe)

---

**En place depuis:** 2026-02-04 10:18 UTC
**Dernier merge:** Aucun (en attente Data Connector)