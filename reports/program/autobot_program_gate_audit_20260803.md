# AUTOBOT — programme 24 couches : audit de gates — 2026-08-03

## Verdict

**GO research/shadow-only.** Les fondations des Blocs 2 à 6 sont présentes et
testées. Elles ne constituent pas une preuve de rentabilité et ne rendent
aucune stratégie éligible au paper ou au live.

Le résultat économiquement correct à ce stade reste le rejet de
`funding_basis` par le gate `NET_SMOKE`. Le système doit donc continuer à
collecter des données et à rejeter les hypothèses faibles, plutôt que chercher
à les optimiser jusqu'à obtenir un résultat flatteur.

## Preuves locales

| Bloc | Périmètre | Résultat |
| --- | --- | --- |
| B02 | Registre append-only, holdout physique, PSR/DSR, trials | `74 passed, 1 skipped` |
| B03 | Portefeuille, capacité, coûts, simulateur shadow | `78 passed` |
| B04 | Artefacts, parité shadow, dérive, quarantaine legacy | `59 passed` |
| B05 | OMS shadow, ledger, réconciliation, TCA | `58 passed, 1 warning` |
| B06 | Résilience, sauvegarde, kill switch, observabilité | `87 passed` |

Le warning du Bloc 5 est une dépréciation de `starlette.testclient`; il ne
change ni les résultats des tests ni les verrous d'exécution.

## Vérification VPS

Contrôle en lecture seule effectué après restauration du VPS :

- source VPS : `5ccb9686da087feffc9f5bcfb03495f0952041b9` ;
- label de l'image : `5ccb9686da087feffc9f5bcfb03495f0952041b9` ;
- image du conteneur = image attendue ;
- `autobot-v2` : `running|healthy` ;
- `/health` : orchestrateur `running`, WebSocket `connected`, une instance
  observation-only ;
- espace disque libre : environ 51.3 GiB ;
- `PAPER_TRADING=false` ;
- `LIVE_TRADING_CONFIRMATION=false` ;
- `STRATEGY_ROUTER_LIVE_ENABLED=false` ;
- `COLONY_AUTO_LIVE_PROMOTION=false` ;
- `AUTOBOT_OBSERVATION_ONLY_RUNTIME=true`.

## État des blocs

| Bloc | État | Limite qui empêche de passer au niveau suivant |
| --- | --- | --- |
| B01 — données/features | PARTIAL | l'historique dérivés backfillé est valable pour la recherche, mais sa parité runtime n'est pas prouvée ; l'historique d'open interest doit continuer à s'accumuler. |
| B02 — alpha/validation | IMPLEMENTED | aucune hypothèse actuelle ne franchit les gates nettes de coûts ; `funding_basis` est rejetée et ne doit pas être relancée sans changement matériel. |
| B03 — portefeuille/simulation | IMPLEMENTED | pas d'alpha validé à évaluer dans cette chaîne. |
| B04 — shadow/gouvernance | IMPLEMENTED | aucune transition automatique vers le paper ou le live n'existe. |
| B05 — OMS/ledger/TCA | IMPLEMENTED pour les scénarios hermétiques | le moteur paper reste volontairement désactivé. |
| B06 — résilience | IMPLEMENTED pour le mode actuel | les sauvegardes retenues attendent une politique de chiffrement et de rétention hors VPS approuvée. |

## Décision de préparation paper

`READY_FOR_HUMAN_PAPER_REVIEW = false`.

Blockers :

1. aucune stratégie n'a une preuve nette de coûts, hors échantillon et
   suffisamment large ;
2. les données dérivées matérialisées ne prouvent pas encore la parité runtime ;
3. l'historique d'open interest est encore une collecte progressive ;
4. aucune approbation humaine de mandat paper limité n'a été donnée ;
5. le programme est explicitement verrouillé en observation-only.

## Suite autorisée

Poursuivre uniquement :

1. la collecte research-only et les checks de fraîcheur/parité ;
2. les hypothèses nouvelles ou matériellement distinctes, via le registre et
   les gates existants ;
3. le durcissement des données/contrats qui réduit un risque identifié.

Interdit sans décision humaine distincte : paper capital, live, dérivés,
short, levier, promotion automatique et envoi d'ordre.
