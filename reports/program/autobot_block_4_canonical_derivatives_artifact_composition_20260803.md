# AUTOBOT Bloc 4 — composition d'artefact spot canonique + dérivés (2026-08-03)

## Décision

`GO_LOCAL_CONTRACT_FIX_ONLY`.

## Correctif

Le constructeur de `StrategyArtifact` recrée l'identité combinée d'un experiment spot/dérivés. Il acceptait uniquement le libellé historique `FEATURE_SNAPSHOT` pour la partie spot, alors que le collecteur canonique produit `CANONICAL_FEATURE_SNAPSHOT`.

La frontière accepte maintenant exactement :

- un snapshot spot `FEATURE_SNAPSHOT` ou `CANONICAL_FEATURE_SNAPSHOT` ;
- un snapshot `DERIVATIVES_POINT_IN_TIME` ;
- sans versions de features dupliquées, comme auparavant.

Tout autre couple ou toute autre cardinalité reste rejeté. L'identité `combined_<fingerprint>` reste calculée avec les mêmes `source_snapshot_id` spot et dérivés que le registre d'expériences.

## Sécurité conservée

Ce correctif ne crée pas d'artefact, ne charge pas de registre, ne démarre pas le runtime et ne modifie aucun flag. Le hand-off multi-source d'un artefact vers shadow reste séparément bloqué jusqu'à sa propre preuve de provenance.

## Validation locale

```text
python -m compileall -q src tests
python -m pytest tests/research/test_shadow_governance.py tests/research/test_manifested_experiment.py tests/research/test_derivatives_spot_context.py tests/research/test_derivatives_feature_snapshot.py tests/research/test_shadow_observation_ledger.py tests/research/test_contract_shadow_pipeline.py tests/research/test_runtime_readiness_assets.py -q
git diff --check
```

Résultat : `80 passed`; compilation et contrôle du diff réussis.

## Déploiement

Le VPS reste hors déploiement tant qu'il est indisponible. Aucun paper capital, live, promotion automatique ou chemin d'ordre n'est autorisé.
