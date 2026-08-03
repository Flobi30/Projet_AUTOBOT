# AUTOBOT Bloc 4 — provenance shadow multi-source (2026-08-03)

## Décision

`GO_LOCAL_SHADOW_EVIDENCE_ONLY`.

## Chaîne vérifiée

Le binder offline accepte un contexte spot/dérivés seulement si :

- les deux vecteurs vérifiés ont le même instant observable ;
- le mapping futures-vers-spot est déclaré comme scellé par le manifest ;
- les snapshots, versions et identité combinée correspondent exactement à l'artefact ;
- le mandat shadow est courant et plafonne le notionnel.

Le preview reconstruit le contexte s'il voit un vecteur dérivés. L'absence du contexte ou une divergence de mapping provoque un rejet machine-readable. Un preview valide produit toujours une `RiskDecision(approved=False)` et aucun `ExecutionCommand`.

Le ledger shadow peut alors écrire les deux vecteurs comme preuve append-only. Il reste séparé du paper ledger.

## Validation locale

```text
python -m compileall -q src tests
python -m pytest tests/research/test_shadow_observation_ledger.py tests/research/test_runtime_shadow_preview.py tests/research/test_shadow_governance.py tests/research/test_derivatives_spot_context.py tests/research/test_derivatives_feature_snapshot.py tests/research/test_contract_shadow_pipeline.py tests/research/test_portfolio_construction.py tests/research/test_strategy_execution_boundary.py tests/test_shadow_paper_adapter_safety.py -q
git diff --check
```

Résultat : `97 passed`; compilation et contrôle du diff réussis.

## Invariants

- Aucun routeur, executor, paper engine ou client Kraken privé n'est importé par le binder.
- Aucun paper capital, live, promotion ou changement de sizing n'est activé.
- Le VPS demeure hors déploiement tant qu'il est indisponible.
