# Audit filtre ATR - AUTOBOT paper

Date: 2026-04-28  
Mode analyse: paper only  
Live trading: non modifie, non active

## Sources utilisees

- `/api/trading/debug` a `2026-04-28T15:52:49Z`
- `/api/opportunities` a `2026-04-28T15:51:34Z`
- Logs runtime `/app/autobot_async.log`
- OHLC public Kraken 1 minute pour le comportement apres signal

## Calcul ATR actuel

Il y a deux filtres ATR distincts.

1. Warm-up instance
   - Fichier: `src/autobot/v2/instance_async.py`
   - Source: `_price_history`
   - Regle: tant que `price_samples < 14`, l'instance expose `atr_vol_warmup`.
   - Impact: aucun signal fiable ne doit etre interprete avant ce warm-up.

2. Gate opportunite
   - Fichier: `src/autobot/v2/opportunity_scoring.py`
   - Seuil actuel: `OPPORTUNITY_MIN_ATR_BPS=18`
   - Calcul: `atr_bps = atr_pct * 10000`
   - `atr_pct` vient de `SignalHandlerAsync._estimate_atr_pct()`.
   - `SignalHandlerAsync._estimate_atr_pct()` calcule une moyenne des mouvements close-to-close sur les derniers ticks, avec un plancher a `0.001`, donc `10 bps`.

Le cas observe est donc simple: les signaux ont un `net_edge` tres positif, mais l'ATR runtime reste au plancher de `10 bps`, sous le seuil `18 bps`. Le scorer donne un bon score global, mais le blocker hard `atr_below_minimum` rend le signal `non_tradable`.

## Cas recents observes

Echantillon: 20 decisions recentes exposees par `/api/trading/debug`.

| Mesure | Valeur |
| --- | ---: |
| Decisions recentes analysees | 20 |
| Signaux avec `net_edge_bps > 50` | 20 |
| Rejetes uniquement par ATR | 20 |
| Symboles | XETHZEUR: 13, XXRPZEUR: 7 |
| Net edge range | 88.828 a 90.640 bps |
| Gross edge range | environ 134.8 a 136.6 bps |
| Cout modele | 46.0 bps |
| ATR estime | 10.0 bps |
| Seuil ATR actuel | 18.0 bps |

Exemples:

| Timestamp UTC | Paire | Prix | Gross bps | Cout bps | Net bps | ATR bps | Rejet |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| 2026-04-28T15:45:15Z | XETHZEUR | 1941.19 | 136.222 | 46.0 | 90.222 | 10.0 | atr_below_minimum |
| 2026-04-28T15:44:42Z | XETHZEUR | 1941.16 | 136.379 | 46.0 | 90.379 | 10.0 | atr_below_minimum |
| 2026-04-28T15:39:28Z | XETHZEUR | 1941.11 | 136.640 | 46.0 | 90.640 | 10.0 | atr_below_minimum |
| 2026-04-28T15:25:04Z | XXRPZEUR | 1.17193 | 135.088 | 46.0 | 89.088 | 10.0 | atr_below_minimum |
| 2026-04-28T15:00:57Z | XXRPZEUR | 1.17195 | 134.915 | 46.0 | 88.915 | 10.0 | atr_below_minimum |

## Simulation paper-only

Hypotheses prudentes:

- Une seule position simulee ouverte par paire.
- Les signaux qui arrivent pendant qu'une position simulee est ouverte sont ignores.
- Entry = prix du signal.
- Target = `entry * (1 + gross_edge_bps / 10000)`.
- Stop conservateur = `entry - 20 bps`, comme le plan d'execution utilise un plancher stop de 0.2%.
- Cout retire du resultat = `46 bps`.
- Horizon disponible au moment de l'audit: environ 58 minutes de donnees 1m Kraken, donc les resultats sont preliminaires.

| Mode | Trades acceptes | Signaux ignores overlap | Winrate | PnL simule | Avg net bps | Max drawdown |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| strict actuel | 0 | 0 | n/a | 0.0000 EUR | n/a | 0.0000 EUR |
| adaptatif | 2 | 18 | 0.0% | -0.1038 EUR | -25.953 bps | -0.1038 EUR |
| opportuniste paper-only | 2 | 18 | 0.0% | -0.1038 EUR | -25.953 bps | -0.1038 EUR |

Details simulation:

| Mode | Paire | Entry | Exit | Outcome | MFE bps | MAE bps | Net pnl bps |
| --- | --- | ---: | ---: | --- | ---: | ---: | ---: |
| adaptatif | XETHZEUR | 1941.33 | 1945.90 | timeout | 24.519 | -14.423 | -22.459 |
| adaptatif | XXRPZEUR | 1.17195 | 1.17389 | timeout | 17.066 | -14.932 | -29.446 |

Lecture: meme avec un edge theorique autour de 90 bps, le marche observe n'a avance que de 17 a 25 bps avant couts dans la fenetre disponible. La target autour de 135 bps n'a pas ete atteinte. Cela soutient l'idee que l'ATR filtre une situation trop calme, plutot qu'un simple seuil arbitrairement trop strict.

## Modes ATR proposes

### 1. strict

Comportement actuel.

- `min_atr_bps = 18`
- Si `atr_bps < 18`, rejet hard.
- Convient au live et au paper stable.
- Avantage: evite les marches qui bougent trop peu pour absorber les couts.
- Defaut: peut rejeter des signaux avec net edge theorique eleve.

### 2. adaptatif

Paper d'abord, live uniquement apres validation longue.

- Base: `min_atr_bps = 18`
- Exception: si `net_edge_bps >= 80`, autoriser `atr_bps >= 10`
- Gardes supplementaires recommandes:
  - score >= 80
  - spread <= 3 bps
  - un seul trade ouvert par paire
  - cooldown apres rejet ou timeout
  - taille reduite

Ce mode respecte l'idee: un net edge tres eleve peut tolerer un ATR plus faible. Mais les chiffres actuels ne prouvent pas encore que ce soit rentable.

### 3. opportuniste paper-only

Mode exploration, jamais live par defaut.

- `net_edge_bps >= 80`
- `atr_bps >= 5`
- ordre paper tres petit
- max 1 position globale ou 1 position par paire
- journalisation obligatoire de chaque decision

Objectif: collecter de la preuve, pas optimiser artificiellement.

## Recommandation prudente

Ne pas changer le mode live et ne pas baisser globalement `OPPORTUNITY_MIN_ATR_BPS`.

Les premiers chiffres disent que le filtre ATR a probablement raison de bloquer ces signaux: le net edge theorique est eleve parce que la target Grid est loin, mais le mouvement reel observe apres signal est trop faible pour couvrir les 46 bps de couts. Le marche ne confirme pas encore la target.

La prochaine etape utile est un test paper-only controle du mode adaptatif, pas pour forcer des trades, mais pour collecter plus de donnees:

- activer seulement en paper
- petit notional
- decision journal active
- exporter chaque decision avec `atr_bps`, `net_edge_bps`, `target_hit`, `stop_hit`, `timeout`, `pnl_net_bps`
- comparer strict/adaptatif/opportuniste sur au moins 24h, idealement 7 jours

Conclusion actuelle: garder `strict` pour le comportement normal. Tester `adaptatif` uniquement en paper si l'objectif est d'apprendre, pas encore pour ameliorer la rentabilite.
