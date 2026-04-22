# Routine pré-merge obligatoire pour chaque PR

## 1) Synchroniser la PR avec la branche cible à jour

Avant toute approbation finale, mettre à jour la branche de travail avec la cible de fusion:

- `main` pour les développements courants
- la branche `release/*` concernée pour une livraison

Exemple (rebase recommandé):

```bash
git fetch origin
git checkout <branche-pr>
git rebase origin/<branche-cible>
```

Alternative (merge):

```bash
git fetch origin
git checkout <branche-pr>
git merge origin/<branche-cible>
```

## 2) Résoudre les conflits correctement

En cas de conflit:

1. Traiter les conflits **fichier par fichier**.
2. Conserver en priorité la logique métier la plus récente et validée.
3. Relancer l'ensemble des vérifications CI locales/PR après résolution.

## 3) Contrôle CI anti-marqueurs de conflit

Un check CI dédié (`Conflict marker scan`) bloque la fusion si des marqueurs de conflit sont trouvés:

- `<<<<<<<`
- `=======`
- `>>>>>>>`

Le scan exclut explicitement les chemins `node_modules`.

## 4) Checklist PR obligatoire

La checklist PR doit inclure et cocher la ligne suivante avant approbation finale:

- `branche synchronisée avec la cible sans conflit`

Cette condition est obligatoire pour toute PR vers une branche critique.
