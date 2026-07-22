# AUTOBOT — Bloc 4 : défauts sans exécution paper

## Décision

`GO` pour le durcissement research/shadow. Les indicateurs legacy de mode
paper peuvent rester nécessaires pour ne jamais basculer vers Kraken, mais ils
ne constituent pas une autorisation d'exécuter, d'allouer ou de promouvoir.

## Changements

Le déploiement Compose force désormais à `false` :

- le bridge shadow/Grid vers l'exécution paper ;
- l'endpoint de test paper ;
- l'autopilote de colonie paper ;
- le scaling automatique d'enfants paper ;
- l'adaptateur paper et le réallocateur de capital, déjà bloqués.

Les valeurs par défaut du control-plane `ColonyConfig` et du routeur Grid sont
elles aussi non autorisantes. Les tests qui modélisent volontairement un ancien
control-plane paper doivent maintenant le demander explicitement.

## Preuve avant déploiement

L'audit lecture seule du ledger runtime n'a trouvé aucune écriture d'ordre ni
de trade récente. Des positions legacy restent à traiter par la réconciliation
existante ; ce changement n'en crée, n'en ferme et n'en modifie aucune.

## Validation locale

```text
python -m compileall -q src
pytest tests/test_colony_manager.py \
       tests/test_deployment_safety_invariants.py \
       tests/test_grid_setup_optimizer_gate.py \
       tests/research/test_archived_grid_defaults.py \
       tests/test_shadow_paper_adapter_safety.py \
       tests/test_paper_capital_reallocator.py -q
```

Résultat : `27 passed`.

## Invariants

- aucun ordre réel ou paper n'est créé ;
- aucune promotion, aucun capital paper et aucun live ne sont activés ;
- Grid reste retiré de l'exécution ;
- la recherche et les observations shadow continuent sans écrire dans le
  ledger paper officiel.
