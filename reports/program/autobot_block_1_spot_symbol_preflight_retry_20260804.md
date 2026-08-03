# AUTOBOT Bloc 1 — retry du préflight spot Kraken (2026-08-04)

## Incident constaté

Le timer `autobot-research-data` est activé mais ses deux derniers cycles ont
échoué durant le préflight `AssetPairs` de Kraken : un timeout HTTPS unique
faisait échouer toute la collecte OHLCV et empêchait le scheduler de recherche
de produire son rapport quotidien.

## Correctif

Le fetch public `AssetPairs` applique maintenant au plus deux retries après
l'appel initial pour les seules erreurs transitoires : timeout/réseau,
throttling et erreurs serveur Kraken. Le délai est borné et exponentiel
(`1s`, puis `2s`).

Les réponses HTTP 4xx permanentes, les payloads non conformes et les erreurs
Kraken déclarées ne sont pas réessayés. Aucun mapping antérieur n'est réutilisé
silencieusement : un échec persistant conserve le cycle en erreur, ce qui
protège l'intégrité des symboles canoniques.

## Validation

```text
python -m pytest \
  tests/research/test_kraken_symbol_mapping.py \
  tests/research/test_daily_data_collection_runner.py \
  tests/research/test_public_collector_boundary.py -q
```

Résultat : `30 passed`.

La couverture vérifie la récupération après deux timeouts, le refus immédiat
d'un HTTP 400, le refus d'un payload malformé, le mapping explicite des
symboles et la frontière public-only.

## Sécurité

- endpoint Kraken public fixe uniquement ;
- aucun fallback de donnée périmée ;
- aucune clé, base runtime, stratégie, ordre, paper ou live impliqué ;
- le système reste research/shadow-only et les échecs persistants restent
  visibles dans systemd.

## Décision

`GO_RESEARCH_COLLECTION_ONLY` après déploiement et contrôle du prochain cycle
timer. Ce correctif n'autorise aucune promotion ni exécution.
