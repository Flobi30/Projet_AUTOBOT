# AUTOBOT Bloc 1 — contexte spot/dérivés vérifié (2026-08-03)

## Décision

`GO_LOCAL_RESEARCH_BOUNDARY_ONLY`.

Ce jalon ajoute un contrat de contexte entre une série spot AUTOBOT et une série perpétuelle Kraken Futures. Il ne crée ni signal, ni ordre, ni activation shadow, paper ou live.

## Preuve ajoutée

`derivatives_spot_context.py` exige :

- un mapping explicite et fingerprinté entre un perpétuel et un spot ;
- une identité `perpetual` distincte de l'identité `spot` ;
- le même actif de base ;
- le même `observed_at` pour les deux vecteurs vérifiés ;
- un snapshot spot canonique et un snapshot dérivés point-in-time distincts ;
- une interdiction structurelle de conversion de prix USD/EUR.

Le constructeur courant relit le manifest dérivés, vérifie son bundle puis recalcule le fingerprint de mapping avant d'accepter `autobot_spot_symbol`. Le contexte expose le marché spot comme unique référence future de PnL et le perpétuel uniquement comme contexte directionnel. Il est immuable, fingerprinté et explicitement `research_only`.

## Validation locale

Les tests ciblés vérifient le mapping BTC/USD perpétuel vers BTC/EUR spot, l'alignement temporel, le rejet des mappings/snapshots invalides et l'absence d'import des chemins runtime ou d'ordre.

Commandes exécutées :

```text
python -m compileall -q src tests
python -m pytest tests/research/test_derivatives_spot_context.py tests/research/test_derivatives_feature_snapshot.py tests/research/test_feature_registry.py tests/research/test_verified_feature_vector.py tests/research/test_verified_feature_vector_publication.py tests/research/test_strategy_research_alpha_adapter.py tests/research/test_contract_shadow_pipeline.py tests/research/test_shadow_observation_ledger.py tests/research/test_funding_basis_research_adapter.py -q
git diff --check
```

Résultat : `73 passed`; compilation et contrôle du diff réussis.

## Limites conservées

- Aucun retour EUR, coût ou fill n'est calculé depuis le prix du perpétuel.
- Aucun `AlphaSignal` n'est créé par ce contrat.
- La stratégie `funding_basis` reste `WAITING_FOR_MORE_DATA` tant que la couverture forward vérifiée et les gates statistiques ne sont pas réunies.
- Le VPS reste hors déploiement tant qu'il est indisponible.
