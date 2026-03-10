# PROMPT DEVIN - CORRECTIONS POST-MERGE PR #51
## Budget: 0.5 ACU (très rapide)

**CONTEXTE:**
La PR #51 a été mergée mais contient des erreurs mineures à corriger. Tu dois faire 3 corrections simples et créer une PR propre.

**REPO:** https://github.com/Flobi30/Projet_AUTOBOT
**BRANCHE:** Créer une nouvelle branche `fix/post-merge-corrections`

---

## TÂCHE 1: Créer requirements-minimal.txt (2 min)

Créer fichier `requirements-minimal.txt` à la racine du repo avec :
```
ccxt>=4.0.0
requests>=2.31.0
```

Ce fichier liste les SEULES dépendances nécessaires pour le bot Grid Trading Kraken.

---

## TÂCHE 2: Corriger dépendance circulaire (5 min)

**Fichier:** `scripts/grid_calculator.py`

**Problème:** Ligne 14, import de get_price crée une dépendance circulaire

**Correction:**

Remplacer :
```python
from get_price import get_current_price, KrakenPriceError
```

Par :
```python
# Import conditionnel pour éviter dépendance circulaire
try:
    from get_price import get_current_price, KrakenPriceError
except ImportError:
    get_current_price = None
    KrakenPriceError = Exception
```

Puis dans la fonction `main()`, ajouter au début :
```python
def main() -> None:
    """Point d'entrée principal: récupère le prix et calcule la grille."""
    config = GridConfig()

    if get_current_price is None:
        print("[ERROR] get_price module non disponible")
        print("Exécutez: pip install requests")
        sys.exit(1)
    
    # ... reste de la fonction inchangé
```

---

## TÂCHE 3: Mettre à jour .gitignore (1 min)

**Fichier:** `.gitignore`

Ajouter à la fin :
```
# Bot state file
bot_state.json
```

---

## TÂCHE 4: Créer PR (2 min)

1. Commit avec message : `fix: requirements-minimal + dépendance circulaire + gitignore`
2. Push branche
3. Créer PR #52
4. Assigner à Flobi30

---

## CRITÈRES DE SUCCÈS:

- [ ] requirements-minimal.txt créé et contient ccxt + requests
- [ ] grid_calculator.py corrigé (import conditionnel + vérif main)
- [ ] .gitignore mis à jour avec bot_state.json
- [ ] PR #52 créée avec description claire

---

## NOTES:

- C'est rapide, 10 minutes max
- Aucune logique complexe, juste des corrections structurelles
- Kimi vérifiera la PR avant que Flo merge

Lance cette tâche maintenant.
