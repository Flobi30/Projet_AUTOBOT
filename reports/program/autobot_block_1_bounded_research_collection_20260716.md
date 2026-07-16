# AUTOBOT — Bloc 1 : collecte research bornée et point-in-time

Décision : `GO` pour la collecte research-only. Cette décision n'autorise ni
paper capital, ni promotion, ni live trading.

## Changement validé

Le collecteur quotidien matérialise désormais le snapshot OHLCV canonique et
son bundle de features immédiatement après la collecte OHLCV. La capture
microstructure, volontairement longue, ne peut donc plus retarder ou faire
perdre ces preuves point-in-time.

Commits déployés :

- `2f924ad4d3f1036fbff5ca2c63de4d2047a45273` — collecte quotidienne bornée ;
- `8755091d1292b0ab30c13146c6641ff0e4a27d82` — matérialisation avant depth ;
- `794dc76c914afc140e7ba1e1420897c99fe4c228` — fondation de tests portable ;
- `6022189be9213f5802166657360217ae9100dc5b` — suppression des faux marquages async.

## Preuves runtime VPS

Le cycle `daily_2026_07_15T18_19_09Z` a terminé avec succès après sa capture
microstructure : il a écrit un manifest OHLCV et un manifest de features,
avec `live_promotion_allowed=false`.

Le cycle suivant, exécutant le code réordonné
`daily_2026_07_16T00_20_07Z`, a fourni les preuves suivantes alors que son
conteneur microstructure fonctionnait encore :

| Élément | Preuve observée |
| --- | --- |
| Manifest OHLCV | écrit à `00:20:33 UTC` |
| Manifest features | écrit à `00:22:32 UTC` |
| OHLCV canoniques | `30 240` lignes, `0` doublon, `0` gap |
| Feature bundle | `120 960` valeurs pour 4 features versionnées |
| Mémoire du job | ~`56 MiB` sur une limite de `1.5 GiB` |
| OOM | aucun événement observé |

Les données restent explicitement research-only. Les premières barres de
chaque groupe produisent des états `WAITING_FOR_MORE_DATA` normaux lorsque le
lookback n'est pas encore atteint ; elles ne sont pas assimilées à un signal.

## Validation

- Tests ciblés collecte/canonical/features : `29 passed`.
- Suite research + CLI : `437 passed`.
- Suite locale complète : `1532 passed, 5 skipped`.
- Suite hermétique VPS en lecture seule : `1600 passed`.
- Compilation Python et contrôle du diff : réussis.

Les skips locaux sont liés aux capacités système indisponibles sous Windows ;
la suite Linux VPS exécute les cas supplémentaires.

## Sécurité vérifiée

- `PAPER_EXECUTION_ADAPTER_ENABLED=false`
- `LIVE_TRADING_CONFIRMATION=false`
- `STRATEGY_ROUTER_LIVE_ENABLED=false`
- `COLONY_AUTO_LIVE_PROMOTION=false`
- `ENABLE_INSTANCE_SPLIT_EXECUTOR=false`
- Aucun ordre, mandat paper ou promotion n'a été activé.
- Le runtime AUTOBOT reste healthy, WebSocket connecté, 14 instances.

## Risques et suite

La capture microstructure conserve volontairement 60 échantillons espacés
d'une minute : un cycle complet dure donc environ une heure. Ce délai ne
retarde plus les données canoniques critiques. Les analyses lourdes restent
isolées du runtime et le scheduler ne peut émettre que des recommandations
research-only.

La suite du Bloc 1 consiste à exploiter ces snapshots pour l'orchestration
research avec provenance complète, sans aucune transition automatique vers le
paper ou le live.
