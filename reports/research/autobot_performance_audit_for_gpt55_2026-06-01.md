# AUTOBOT Performance Audit Brief For GPT-5.5

Date: 2026-06-01
Repository: `Flobi30/Projet_AUTOBOT`
Observed local commit: `3d1edd9`
Mode: `paper-first`
Live trading: disabled

## Copy-Paste Prompt

Tu es GPT-5.5. Tu dois auditer AUTOBOT, un systeme de trading algorithmique crypto sur Kraken spot EUR, paper-first, avec objectif de recherche, backtest, validation et paper trading robuste.

Objectif: determiner pourquoi AUTOBOT ne produit pas encore une performance robuste malgre plusieurs couches de logique: grid, trend, mean reversion, opportunity scoring, regime detection, shadow labs, validation quant, risk guards et dashboard. Ne cherche pas une strategie miracle. Ne propose pas de passage live. Ne baisse pas les seuils pour forcer des trades. Le but est d'identifier ce qui doit etre corrige pour mesurer correctement, filtrer, rejeter, comparer et seulement ensuite ameliorer.

## Contexte Technique

Pipeline cible:

`MarketData -> Signal -> OpportunityScore -> PortfolioAllocation -> RiskCheck -> ExecutionCommand -> Fill -> Position -> PnL -> Ledger -> Dashboard`

AUTOBOT contient deja:

- orchestrateur async;
- TradingInstanceAsync;
- strategies grid, trend, mean reversion;
- opportunity scoring;
- scoring regime Markov/entropy;
- modules risk/cost guard;
- Kelly criterion, ATR trailing stop, BlackSwanCatcher;
- shadow labs grid/trend/mean reversion;
- validation quant;
- event-driven replay/research harness;
- validation matrix CLI;
- registry de strategies et promotion gate;
- loss attribution.

Important: le systeme est devenu riche, mais la performance n'est pas encore validee. Il faut eviter d'ajouter de nouvelles couches tant que la mesure, l'execution simulee, les couts, le ledger, les baselines et le workflow de promotion ne sont pas solides.

## Etat De Securite

- Live trading non autorise.
- Aucune strategie ne doit pouvoir passer live automatiquement.
- Les statuts `learning`, `candidate` ou `shadow_only` ne doivent jamais envoyer d'ordre reel.
- Les resultats shadow/backtest ne sont pas des preuves suffisantes pour live.
- Toute promotion critique doit rester soumise a validation humaine.

## Donnees Et Runs Recents

Source principale recente:

- Copie read-only VPS de `/opt/Projet_AUTOBOT/data/autobot_state.db`.
- Fenetre de donnees: `2026-05-27T20:25:09Z` a `2026-06-01T11:55:57Z`.
- Univers teste: 14 paires EUR.
- Strategies testees: `grid`, `trend`, `mean_reversion`.
- Matrix: 42 cellules strategy/symbol.
- 42 cellules executees avec succes.
- 0 erreur runtime.
- Couts inclus via le research cost model configure.

Paires:

`TRXEUR`, `SOLEUR`, `ETHZEUR`, `BTCZEUR`, `LTCZEUR`, `XLMZEUR`, `XRPZEUR`, `ADAEUR`, `LINKEUR`, `DOTEUR`, `BCHEUR`, `ATOMEUR`, `AVAXEUR`, `AAVEEUR`.

## Resultats Validation Matrix 2026-06-01

| Strategy | Registry ID | Current Status | Recommended Status | Passing Symbols | Closed Trades | Net PnL | Best PF | Worst DD | Live Allowed |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| grid | dynamic_grid | candidate | rejected | 0/14 | 391 | -190.493353 | 0.305394 | 7.191241 | false |
| mean_reversion | mean_reversion | learning | rejected | 0/14 | 706 | -353.386757 | 0.283037 | 4.589784 | false |
| trend | trend_momentum | learning | rejected | 0/14 | 221 | -115.803564 | 0.540026 | 6.801713 | false |

Interpretation:

- Aucune famille de strategie ne passe sur les 14 paires.
- Les meilleurs profit factors restent tres inferieurs a 1.0.
- `mean_reversion` est la plus active et la plus destructrice en PnL total.
- `trend` trade moins, perd moins, mais ne couvre toujours pas les couts.
- `grid` reste negatif avant et apres couts.
- `XLMZEUR` est particulierement destructrice dans cet echantillon, mais cela ne veut pas dire que la paire est "mauvaise" en absolu; cela signifie que la logique actuelle ne s'adapte pas bien a son comportement observe.

## Loss Attribution 2026-06-01

Scope:

- 42 trade journals analyses.
- 0 journal manquant.
- 1,318 trades research clotures.

Resultat global:

| Metric | Value |
| --- | ---: |
| Gross PnL before modeled costs | -237.923673 |
| Net PnL after costs | -659.683673 |
| Total modeled cost | 632.640000 |
| Cost-flipped trades | 301 |

Par famille:

| Strategy | Trades | Gross PnL | Net PnL | Cost | Cost-Flipped Trades |
| --- | ---: | ---: | ---: | ---: | ---: |
| grid | 391 | -65.373353 | -190.493353 | 187.680000 | 78 |
| trend | 221 | -45.083564 | -115.803564 | 106.080000 | 24 |
| mean_reversion | 706 | -127.466757 | -353.386757 | 338.880000 | 199 |

Worst cells:

| Symbol | Strategy | Trades | Gross PnL | Net PnL | Cost | Cost-Flipped | Worst Exit | Worst Entry |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- | --- |
| XLMZEUR | grid | 211 | -4.338183 | -71.858183 | 101.280000 | 26 | grid_stop_loss | grid_support_touch |
| XLMZEUR | trend | 121 | -21.605366 | -60.325366 | 58.080000 | 8 | trend_exit | trend_breakout |
| XLMZEUR | mean_reversion | 109 | -11.017837 | -45.897837 | 52.320000 | 15 | mean_reversion_stop | mean_reversion_zscore_entry |
| BCHEUR | mean_reversion | 53 | -20.012221 | -36.972221 | 25.440000 | 13 | mean_reversion_stop | mean_reversion_zscore_entry |
| SOLEUR | mean_reversion | 66 | -11.233881 | -32.353881 | 31.680000 | 20 | mean_reversion_exit | mean_reversion_zscore_entry |

Lecture importante:

- Le probleme n'est pas seulement les frais/spread/slippage.
- Le gross PnL est deja negatif avant couts.
- Les couts aggravent ensuite fortement le resultat.
- 301 trades sont retournes par les couts: direction pas toujours catastrophique, mais objectifs trop proches du cout reel.
- Les entrees et sorties semblent faibles: mauvaise direction, mauvais timing de sortie, objectifs trop petits, ou regime mal filtre.

## Resultats Paper Officiels Connus Au 2026-05-31

Source de verite officielle paper: `trade_ledger`.

- Closed trades officiels: 555.
- PnL net officiel total: -21.397803 EUR.
- Profit factor officiel: 0.361.
- Win rate officiel: 26.85%.
- Expectancy moyenne: -0.038555 EUR/trade.
- Frais sur clotures: 10.183481 EUR.

Interpretation:

AUTOBOT tourne, observe et execute en paper, mais la strategie officielle paper n'a pas encore une esperance positive.

## Ancienne Divergence Importante Shadow vs Official Paper

Avant les derniers runs research, les shadow labs montraient des resultats positifs sur `XXLMZEUR`, surtout en grid:

- `XXLMZEUR / grid_wide`: 139 closes, +24.300082 EUR.
- `XXLMZEUR / grid_balanced`: 155 closes, +19.423937 EUR.
- `XXLMZEUR / grid_tight_range`: 162 closes, +18.584146 EUR.
- `XXLMZEUR / grid_defensive_observe`: 143 closes, +15.481636 EUR.
- `XXLMZEUR / grid_volatility`: 145 closes, +14.136190 EUR.

Mais les runs research recents sur donnees runtime montrent `XLMZEUR` tres negatif dans les trois familles.

Question critique:

Est-ce que la divergence vient de:

- shadow fill model trop optimiste;
- hypotheses de couts differentes;
- mismatch de symboles `XXLMZEUR` vs `XLMZEUR`;
- official routing qui ne selectionne pas la bonne variante;
- conditions de marche differentes;
- accounting mismatch;
- exits mal simulees;
- donnees/order book insuffisantes;
- look-ahead ou bias dans shadow;
- execution officielle paper trop pessimiste ou buggee?

## Etat Du Harnais De Validation

Deja en place:

- `research_validation_harness.py`: replay event-driven isole.
- `market_data_repository.py`: chargement/normalisation de donnees.
- `execution_cost_model.py`: fees, spread, slippage, rejets.
- `trade_journal.py`: journal standardise.
- `metrics_engine.py`: PnL net/brut, PF, winrate, drawdown, expectancy, etc.
- `backtest_engine.py`: backtests simples reproductibles.
- `walk_forward.py`: validation walk-forward.
- `validation_matrix.py`: matrix multi-strategies/multi-symboles.
- `registry_recommendations.py`: recommandations conservatrices sans promotion live.
- `loss_attribution.py`: attribution des pertes/couts.

Limites actuelles:

- Donnees surtout issues de `market_price_samples`, pas encore d'OHLCV/depth historique riche.
- Execution simulee encore simplifiee: pas de queue position, partial fill profond, market impact complet.
- Regime split disponible partiellement mais pas encore decisionnel de maniere prouvee.
- Pas encore de walk-forward massif sur donnees longues.
- Pas encore de reconciliation complete officielle paper vs shadow trade par trade.
- Pas encore de diagnostics MFE/MAE systematiques par trade pour savoir si le probleme principal est entree, sortie ou taille du target.

## Hypotheses Racines A Classer

Classe ces hypotheses par probabilite et propose comment les confirmer:

1. Les signaux actuels n'ont pas d'edge brut positif.
   - Preuve actuelle: gross PnL research negatif avant couts.

2. Les targets sont trop proches des couts.
   - Preuve actuelle: 301 cost-flipped trades.

3. Mean reversion sur-declenche dans des regimes non adaptes.
   - Preuve actuelle: 706 trades et plus gros net loss.

4. Grid entre sur support-touch trop faible et sort trop souvent en stop.
   - Preuve actuelle: `grid_support_touch` -> `grid_stop_loss` sur worst cell.

5. Trend breakout arrive trop tard ou confirme mal.
   - Preuve actuelle: `trend_breakout` -> `trend_exit`, PF max seulement 0.54.

6. Shadow labs etaient trop optimistes.
   - Preuve actuelle: divergence historique shadow positif vs official/research negatif.

7. Le router/gouvernance ne choisit pas les bonnes variantes au bon moment.
   - A verifier contre logs decision_ledger, signal_outcomes, setup shadow lab, strategy_router.

8. Donnees marche insuffisantes ou trop bruitees.
   - A verifier: order book freshness, spread reel, backpressure websocket, invalid books, timestamp alignment.

9. Accounting ou ledger officiel incoherent.
   - A verifier: fills, sells cancelled, open/closed positions, fees both sides, realized vs unrealized.

10. Trop de complexite avant validation.
   - A verifier: modules ML/sentiment/ensemble influencent-ils la decision sans preuve OOS?

## Questions D'Audit A Resoudre

1. Le PnL negatif vient-il surtout:
   - des entrees;
   - des sorties;
   - des couts;
   - du regime;
   - du routing;
   - de l'execution;
   - de l'accounting?

2. Les trades perdants avaient-ils une MFE positive suffisante?
   - Si oui: probleme d'exit/TP/trailing.
   - Si non: probleme d'entree/signal/regime.

3. Les winners potentiels sont-ils coupes trop tot ou laisses trop peu courir?

4. Les stops sont-ils places dans le bruit normal de la paire?

5. Chaque strategie bat-elle au moins:
   - no-trade;
   - buy-and-hold;
   - random same-frequency;
   - previous/default baseline?

6. La performance depend-elle d'une seule paire ou d'un seul regime?

7. Les couts utilises sont-ils realistes pour Kraken spot EUR?

8. Les paires choisies ont-elles assez de liquidite/spread pour scalping/grid?

9. Le harnais replay produit-il les memes conclusions que le paper officiel?

10. Quelle modification minimale permettrait de tester l'hypothese la plus probable sans ajouter de complexite?

## Ce Que Je Veux Comme Reponse

Produis:

1. Diagnostic priorise.
2. Tableau des causes probables avec preuves actuelles et donnees manquantes.
3. Requetes SQL ou analyses a lancer pour confirmer.
4. Changements minimaux recommandes.
5. Changements a eviter.
6. Plan experimental paper-only.
7. Criteres mesurables pour dire que la performance s'ameliore.
8. Verdict live-readiness.

Le verdict attendu doit etre prudent: AUTOBOT n'est pas live-ready tant que PF, PnL net, baselines, walk-forward, paper official et reconciliation ne sont pas positifs et coherents.

## Changements A Eviter

- Ne pas activer live.
- Ne pas baisser globalement les seuils.
- Ne pas augmenter agressivement la taille pour masquer une expectancy negative.
- Ne pas ajouter du ML avant de prouver que les baselines et le ledger sont fiables.
- Ne pas promouvoir une strategie positive en shadow si elle est negative en official paper/replay.
- Ne pas optimiser sur la derniere fenetre uniquement.
- Ne pas traiter `XLMZEUR` ou `TRXEUR` comme "bonne/mauvaise paire" sans regime, couts et periode.

## Prochaine Action Recommandee

Avant toute nouvelle strategie:

1. Ajouter diagnostics MFE/MAE par trade dans le journal de backtest/replay.
2. Comparer MFE/MAE vs couts et TP/SL distance.
3. Rejouer les 14 paires avec ces diagnostics.
4. Identifier si les pertes viennent principalement:
   - d'entrees sans excursion favorable;
   - de bonnes entrees mal sorties;
   - de couts trop proches du target;
   - de regime mauvais;
   - de router/gouvernance.
5. Ensuite seulement modifier les strategies ou le routing.

Phrase cle:

AUTOBOT ne doit pas trader plus pour gagner plus. Il doit d'abord prouver que chaque famille de strategie produit une expectancy nette positive, stable, apres couts, contre baselines, sur donnees hors echantillon.
