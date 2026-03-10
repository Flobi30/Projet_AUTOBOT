# PROCÉDURE D'AUDIT - AUTOBOT
## À appliquer RIGOUREUSEMENT à chaque PR

---

## CHECKLIST PRÉ-AUDIT

### 1. Vérifier les imports (TOUJOURS)
```bash
cd /home/node/.openclaw/workspace/autobot
python3 -c "
import sys
sys.path.insert(0, 'scripts')
# Tester tous les imports du nouveau fichier
try:
    from NEW_MODULE import NEW_CLASS
    print('✅ Import OK')
except Exception as e:
    print(f'❌ Import ERROR: {e}')
"
```

### 2. Vérifier la cohérence des dépendances
- [ ] Les imports pointent vers les bons fichiers
- [ ] Pas de références à `src/grid_engine/` depuis `scripts/`
- [ ] Les classes utilisées existent et ont les bonnes signatures

### 3. Tester l'exécution basique
```bash
python3 scripts/NEW_FILE.py --help 2>&1 | head -20
```

---

## CHECKLIST POST-MERGE (AVANT DE DIRE "ÇA MARCHE")

### 1. Vérifier les fichiers créés/modifiés
```bash
git log --oneline -3
git show --name-only HEAD
```

### 2. Vérifier que le code s'exécute
```bash
# Test syntaxe
python3 -m py_compile scripts/FICHIER.py

# Test imports
python3 -c "import sys; sys.path.insert(0, 'scripts'); import FICHIER"
```

### 3. Vérifier l'intégration
- [ ] Les nouveaux fichiers sont appelés par quelqu'un ?
- [ ] Il existe un chemin d'exécution qui utilise ce code ?
- [ ] Pas de code mort (fonctions jamais appelées)

### 4. Vérifier la persistance (si applicable)
- [ ] Les fichiers de state sont créés
- [ ] Les données sont sauvegardées correctement
- [ ] La reprise après redémarrage fonctionne

### 5. Vérifier les logs
- [ ] Les logs sont informatifs
- [ ] Les erreurs sont capturées et loguées
- [ ] Pas de print() sauvages

---

## TEMPLATE RAPPORT D'AUDIT

```markdown
## AUDIT PR #XX - [TITRE]

### ✅ Vérifications faites:
1. **Imports:** [OK / ERREUR - détails]
2. **Syntaxe:** [OK / ERREUR - détails]
3. **Intégration:** [OK / ERREUR - détails]
4. **Tests:** [OK / ERREUR - détails]

### 📊 Couverture:
- Fichiers modifiés: [liste]
- Nouveaux fichiers: [liste]
- Fichiers supprimés: [liste]

### 🔍 Problèmes trouvés:
- [ ] Aucun
- [ ] Mineurs: [détails]
- [ ] Majeurs: [détails]
- [ ] Bloquants: [détails]

### 🎯 Verdict:
- [ ] ✅ PR approuvée
- [ ] ⚠️ PR approuvée avec réserves
- [ ] ❌ PR rejetée - corrections nécessaires

### 💡 Recommandations:
[Si applicable]
```

---

## RÈGLES D'OR

1. **JAMAIS** dire "ça marche" sans avoir testé l'exécution
2. **JAMAIS** merger sans vérifier les imports
3. **TOUJOURS** tester le chemin complet (main → fonctions)
4. **TOUJOURS** vérifier que le code est appelé (pas de code mort)
5. **SI DOUTE** → demander des clarifications, pas merger à l'aveugle

---

## RAPPEL DES COÛTS ACUs

- 1 PR simple (1 fichier, <100 lignes): ~0.5-1 ACU
- 1 PR moyenne (2-3 fichiers, <300 lignes): ~1-2 ACUs
- 1 PR complexe (architecture, >500 lignes): ~3-5 ACUs

**Si une PR dépasse le budget estimé → ALERTER Flo immédiatement**

---

*Dernière mise à jour: 2026-02-06*
*Responsable: Kimi (OpenClaw)*
