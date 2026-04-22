# KPI officiels (AUTOBOT)

Ce document définit les formules de référence pour les KPI affichés et monitorés.

## 1) Rendement (Return / ROI)

- **Entrées**:
  - `total_profit` = profit/perte cumulé(e)
  - `total_invested` = capital réellement engagé (dénominateur)
- **Formule**:

```text
rendement_pct = (total_profit / total_invested) * 100
```

- **Règle de garde**:
  - Si `total_invested <= 0`, le rendement est remplacé par un fallback explicite (`0.0` côté UI), pour éviter division par zéro ou ratio incohérent.

## 2) Drawdown maximum (Max Drawdown)

- **Entrées**:
  - Série d'équité `equity_t`
  - Plus haut historique courant `peak_t = max(equity_0..equity_t)`
- **Drawdown instantané**:

```text
drawdown_t = (equity_t - peak_t) / peak_t
```

- **Max Drawdown**:

```text
max_drawdown = min(drawdown_t)
```

> Convention: exprimé en pourcentage négatif (ex: `-12.4%`), ou en valeur absolue selon le contexte d'affichage.

## 3) Profit Factor (PF)

- **Entrées**:
  - `gross_profit` = somme des trades gagnants (> 0)
  - `gross_loss` = valeur absolue de la somme des trades perdants
- **Formule**:

```text
profit_factor = gross_profit / gross_loss
```

- **Règles de garde**:
  - Si `gross_loss == 0` et `gross_profit > 0` alors PF peut être traité comme `+∞` (ou borné pour l'affichage).
  - Si `gross_profit == 0` et `gross_loss == 0`, PF est non défini; afficher une valeur neutre (`—`) ou fallback explicite.
