# AUTOBOT - programme 24 couches : audit des gates au 2026-07-26

Decision : `GO_RESEARCH_COLLECTION_WAITING_FOR_MATERIAL_DATA`.

Ce rapport est une preuve de controle, pas une autorisation de shadow, de paper
capital, de promotion ou de live. Les flags et les chemins d'ordre restent
inchanges.

## Perimetre et preuves verifiees

- Code audite : `8345ac3c5f5d042bc9f9d289cd1e578b0c9dba9b`
  (`Record official Q1 OHLCVT research snapshot`).
- Tests de garde-fou rejoues sur ce commit : `97 passed` : resilience,
  readiness, gouvernance des artefacts, shadow, contrats, simulateur,
  registre d'experiences et securite de production.
- Suite complete deja executee apres le meme ensemble de changements :
  `1881 passed, 6 skipped`; compilation Python et `git diff --check` passes.
- Le VPS, le checkout Git et l'image Docker etaient alignes sur ce commit.
  Le conteneur `autobot-v2` etait healthy, son WebSocket connecte et ses
  14 instances visibles.
- Flags confirmes inactifs :
  `LIVE_TRADING_CONFIRMATION=false`,
  `STRATEGY_ROUTER_LIVE_ENABLED=false`,
  `COLONY_AUTO_LIVE_PROMOTION=false`,
  `PAPER_EXECUTION_ADAPTER_ENABLED=false`.

## Audit non autorisant des artefacts strategie

L'audit a ete execute sur le VPS dans un conteneur jetable sans reseau,
filesystem racine en lecture seule, privileges Linux supprimes et copies SQLite
temporaires verifiees. Il ne lit jamais directement une base active et ne
demarre pas le runtime.

Resultat : `NO_SHADOW_ARTIFACT_CANDIDATE`.

| Element | Valeur constatee |
| --- | --- |
| Registre d'experiences | schema `CURRENT`, integrite SQLite `ok`, 0 violation FK |
| Source du snapshot changee pendant la copie | `false` |
| Experiences | 4 |
| Registre d'artefacts distinct | absent / 0 artefact |
| Artefacts prets a enregistrer | 0 |
| Shadow lance | `false` |
| Ordre cree | `false` |
| Paper capital / live / promotion auto | tous `false` |

Les quatre experiences restent fail-closed :

| Hypothese / template | Etat le plus recent | Consequence |
| --- | --- | --- |
| `long_trend` / `regime_filtered_trend` | `DATA_CHECK / PASSED` | preuves terminales shadow, holdout immuable et artefact absentes |
| `long_trend` / `regime_filtered_trend` | `NET_SMOKE / REJECTED` | rejet terminal, aucune relance implicite |
| `funding_basis` / `funding_extreme_reversion` | `NET_SMOKE / INSUFFICIENT_DATA` | attente de donnees materielles, avec plancher de trials conserve |
| `funding_basis` / `funding_extreme_reversion` | `NET_SMOKE / REJECTED` | rejet terminal, aucune relance implicite |

## Couverture des 24 couches

`docs/architecture/layer_coverage.json` reste volontairement integralement
`PARTIAL`. Ce statut ne nie pas le code ni les tests : il signifie que la
preuve de production exigee par chaque couche n'est pas encore suffisamment
complete pour rendre un resultat de recherche executable.

Le dossier de readiness genere depuis cette matrice est donc, correctement :

```text
NOT_READY_FOR_HUMAN_PAPER_REVIEW
```

Les bloqueurs prioritaires sont les couches de temporalite et features (3, 5),
registre et validation statistique (10--12), portefeuille/couts/simulation
(13, 15--17), gouvernance/shadow/paper/risque (18--21), OMS-ledger-TCA
(22--23) et resilience (24). Les tests de ces composants existent, mais un
label `VERIFIED` demanderait en plus des donnees continues, un artefact
strategie eligible, une parite runtime et des preuves operationnelles actuelles.

## Donnees actuelles et gate de recherche

Le snapshot officiel Kraken Q1 2026 documente dans
`reports/program/autobot_block_1_official_q1_ohlcvt_research_snapshot_20260726.md`
est un progres material de qualite, mais il ne contient qu'un trimestre :

- BTC/EUR et ETH/EUR, 5m, 15m et 1h ;
- 73 428 lignes canoniques, huit gaps, aucun doublon ;
- features deterministes materialisees et parite batch/shadow de calcul
  verifiee ;
- absence volontaire de parite runtime et aucune fusion avec les donnees
  operationnelles plus recentes.

Ce trimestre ne peut pas etre traite comme six mois continus ou comme une
preuve qu'une strategie rejetee est devenue valide. L'archive officielle
complete n'a pas ete automatisee, car le fournisseur renvoie actuellement une
page de quota/confirmation et non un ZIP verifiable. Le programme ne contourne
pas cette restriction et ne depend pas d'un telechargement fragile.

## Prochaine action autorisee

1. Continuer uniquement les collectes research deja isolees et les snapshots
   forward de donnees publiques.
2. Rechercher une periode officielle supplementaire de facon bornee et
   verifiable. Toute archive apportee manuellement doit etre importee dans un
   nouveau snapshot separe, avec manifest, fingerprint, gaps et mapping exact.
3. N'enregistrer un successeur de recherche que si la signature de donnees est
   materiellement nouvelle et qu'une these/template est explicitement
   pre-enregistre. Les rejets precedents et leur charge de multiple testing
   restent applicables.
4. Lancer alors seulement `DATA_CHECK`; aucun resultat de cette etape ne peut
   activer shadow, paper ou live.

## Invariants

- Aucun ordre, endpoint prive Kraken, cle, sizing, levier ou capital paper n'a
  ete utilise ou modifie par cet audit.
- Grid et aliases restent retires et exclus du ledger officiel.
- Toute absence de donnees ou de preuve reste `DATA_MISSING`,
  `WAITING_FOR_MORE_DATA` ou `INSUFFICIENT_DATA`, jamais une estimation
  optimiste.
