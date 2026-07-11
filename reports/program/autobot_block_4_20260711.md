# AUTOBOT — Bloc 4 : gouvernance shadow et surveillance de dérive

## Décision

`GO` pour la gouvernance research/shadow. Aucune stratégie n'est promue, aucun
capital paper n'est activé et le live reste hors scope.

## Livré

- `StrategyArtifact` fige stratégie, version, commit, snapshot, versions de
  features, paramètres, mandat et manifeste de validation.
- Les artefacts et décisions de sécurité sont stockés dans un registre SQLite
  append-only, avec refus de toute suppression ou modification.
- Les aliases grid ne peuvent exister que dans l'état `RETIRED`.
- La parité batch/shadow compare l'artefact, le snapshot, les features, la
  fraîcheur et le fingerprint de `TargetPortfolio`.
- La surveillance évalue échantillon, PF/expectancy rolling, drawdown, dérive
  des features, coût et fraîcheur des données.
- Les seules transitions automatiques possibles sont : `WATCH`, `REDUCE`,
  `DISABLE_NEW_ENTRIES` et `QUARANTINE`. Une décision ne peut jamais diminuer
  automatiquement sa sévérité ni démarrer le shadow depuis `RESEARCH`.

## Invariants

- Aucun import de routeur, handler runtime ou moteur paper dans le module.
- `paper_capital_allowed`, `live_allowed` et `automatic_promotion_allowed`
  sont systématiquement `false` dans les artefacts et les événements.
- Une donnée périmée, une parité manquante ou une dérive sévère bloque/réduit
  l'observation ; rien n'augmente le risque automatiquement.

## Risques résiduels

- Le runtime legacy ne consomme pas encore ces artefacts. Il reste donc
  `UNSAFE` pour toute décision paper, malgré la gouvernance research livrée.
- Les règles de promotion humaine et le raccord runtime seront uniquement
  envisagés après correction des bypass et du cycle OMS/ledger.
