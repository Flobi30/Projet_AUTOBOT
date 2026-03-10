# PROTOCOLE_DEVIN.md - Règles pour les sessions Devin

**Date:** 2026-02-06  
**Version:** 1.0  
**Statut:** Obligatoire pour toute session Devin

---

## 🎯 RÈGLE D'OR (Ajoutée le 2026-02-06)

> **Chaque PR doit inclure des tests automatisés qui valident les aspects fonctionnels.**
>
> **INTERDIT de demander à l'humain de "vérifier manuellement" ou "tester".**

---

## 📋 CHECKLIST OBLIGATOIRE POUR CHAQUE PR

### ✅ Avant de créer la PR, Devin doit vérifier :

- [ ] **Tests unitaires** pour la logique métier
- [ ] **Tests d'intégration** si plusieurs modules interagissent
- [ ] **Tests de messages d'erreur** - Vérifier que les messages sont clairs et complets
- [ ] **Tests de cas limites** (edge cases)
- [ ] **Tous les tests passent** en CI/CD (6/6 checks verts)

### ❌ INTERDIT dans une PR :

- ❌ "Vérifiez que..." → Remplacer par un test automatique
- ❌ "Testez manuellement..." → Remplacer par un test automatique
- ❌ "Confirmez que..." → Remplacer par un test automatique
- ❌ "Le reviewer doit vérifier..." → Remplacer par un test automatique

---

## 🧪 EXEMPLES DE TESTS À IMPLÉMENTER

### Exemple 1 : Message d'erreur
```python
# AVANT (interdit - demande à l'humain):
# "Vérifiez que le message d'erreur est acceptable"

# APRÈS (obligatoire - test automatique):
def test_error_message_complete():
    """Vérifie que le message d'erreur mentionne toutes les causes possibles."""
    with patch('builtins.print') as mock_print:
        with pytest.raises(SystemExit):
            main()  # Sans get_price disponible
        
        output = ' '.join([call[0][0] for call in mock_print.call_args_list])
        assert "get_price.py" in output, "Message doit mentionner get_price.py"
        assert "requests" in output, "Message doit mentionner requests"
```

### Exemple 2 : Validation de données
```python
# AVANT (interdit):
# "Vérifiez que les niveaux sont correctement calculés"

# APRÈS (obligatoire):
def test_grid_levels_count():
    """Vérifie qu'on a bien 15 niveaux."""
    levels = calculate_grid_levels(55000.0, config)
    assert len(levels) == 15
    
def test_grid_has_center():
    """Vérifie qu'il y a un niveau CENTER au milieu."""
    assert levels[7].level_type == "CENTER"
```

### Exemple 3 : Import conditionnel
```python
# AVANT (interdit):
# "Testez avec et sans le module disponible"

# APRÈS (obligatoire):
def test_import_error_handling():
    """Vérifie le comportement quand l'import échoue."""
    # Simule ImportError
    with patch.dict('sys.modules', {'get_price': None}):
        reload(grid_calculator)
        assert grid_calculator.get_current_price is None
```

---

## 📝 TEMPLATE DE PROMPT DEVIN

**À inclure systématiquement dans chaque prompt :**

```markdown
## RÈGLE CRITIQUE - TESTS AUTOMATIQUES

- Ne demande JAMAIS à l'humain de "vérifier" ou "tester" manuellement
- Chaque fonctionnalité doit avoir son test automatique
- Les tests doivent couvrir :
  * Cas nominal (happy path)
  * Cas d'erreur (messages, exceptions)
  * Cas limites (valeurs min/max, None, etc.)
  * Imports conditionnels

- Si tu écris un message d'erreur → teste-le
- Si tu crée une fonction → teste-la
- Si tu modifies un comportement → teste-le

**Format livrable :**
1. Code modifié/créé
2. Tests automatiques associés
3. CI/CD passe (6/6 verts)
4. **AUCUNE** instruction "vérifiez manuellement" dans la PR description
```

---

## 🔍 CONTRÔLE QUALITÉ (Par Kimi)

### À chaque PR reçue :

1. **Vérifier** qu'il y a des tests automatiques
2. **Vérifier** qu'aucun "vérifiez" manuel n'est demandé
3. **Si problème** → demander correction avant merge

### Si Devin demande une vérification manuelle :

**Action immédiate :**
```
"Rejette cette PR. Remplace la vérification manuelle par un test 
automatique. Ne demande jamais à l'humain de tester - c'est le 
travail des tests CI/CD."
```

---

## 💡 POURQUOI CETTE RÈGLE ?

**Problème identifié le 2026-02-06 :**
- Devin créait des PR avec CI/CD verts
- Mais demandait à Flo de "vérifier manuellement" des choses
- Résultat : problèmes découverts après merge

**Solution :**
- Automatiser TOUTES les vérifications
- La CI/CD doit valider, pas l'humain
- "La confiance n'exclut pas le contrôle" → mais le contrôle doit être automatique

---

## 📊 MÉTRIQUES

**Objectif :**
- 0 PR avec "vérifiez manuellement"
- 100% des fonctionnalités testées automatiquement
- CI/CD comme seul juge de qualité

---

**Dernière mise à jour:** 2026-02-06  
**Prochaine revue:** Après chaque problème découvert post-merge
