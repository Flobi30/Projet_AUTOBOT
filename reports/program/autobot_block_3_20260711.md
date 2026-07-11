# AUTOBOT — Bloc 3 : portefeuille, coûts, capacité et simulation

## Décision

`GO` pour la fondation research/shadow, sans stratégie `SHADOW_ELIGIBLE` et
sans aucune activation paper ou live. Le raccord du runtime legacy aux contrats
reste explicitement **UNSAFE** et sera traité comme un bloqueur avant toute
revue paper humaine.

## Audit indépendant

Le Bloc 3 a constaté deux écarts importants entre l'architecture cible et le
runtime existant :

- les contrats v1 (`AlphaSignal`, `TargetPortfolio`, `OrderIntent`,
  `RiskDecision`) ne sont pas encore le chemin de production ;
- le handler historique peut contourner l'allocation centralisée, les mandates
  et le risque v2 avant l'exécuteur.

Le paper historique reste non fiable comme preuve d'exécution : contraintes
Kraken par paire, fills partiels, timeouts, stops et profondeur ne sont pas
encore uniformément reproduits. Aucun de ces chemins n'a été activé, assoupli
ou contourné par ce bloc.

## Livré, research-only

- `portfolio_construction.py` : construction déterministe d'un
  `TargetPortfolio` depuis des `AlphaSignal` disponibles point-in-time.
  Seuls les signaux spot, long-only et de même devise de cotation que le cash
  sont acceptés. Les conversions implicites, shorts, données futures et edges
  insuffisants sont rejetés avec une raison explicite.
- Capacité : la taille est comparée à une participation maximale de liquidité
  réellement observée. En l'absence de profondeur/volume, le résultat est
  `WAITING_FOR_MORE_DATA`, jamais une hypothèse de capacité.
- `execution_simulator.py` : simulation shadow contractuelle avec latence,
  données périmées, fill partiel, refus, expiration et reprise déterministe.
- Trois scénarios de coût : central, pessimiste et stress, à partir du modèle
  de coût research commun.
- Règles de marché explicites : le simulateur exige une capture publique des
  contraintes Kraken par paire (`ordermin`, `costmin`, précision volume/prix).
  Sans elles, l'intention est refusée.
- La matrice des 24 couches reflète les états réels : portefeuille runtime et
  paper historique sont `UNSAFE`; capacité et simulateur research sont
  `PARTIAL` avec des tests associés.

## Invariants

- Aucun import du routeur d'ordres, du handler runtime ou de l'exécuteur live
  dans les nouveaux modules research.
- Le simulateur refuse tout `OrderIntent` paper ou live.
- Il n'émet jamais d'`ExecutionCommand` et ne touche ni au paper ledger ni au
  runtime.
- Les règles de marché absentes, la donnée de liquidité absente ou une donnée
  périmée empêchent un fill.

## Tests locaux

- Portefeuille/capacité/simulateur/coûts/parité ciblée : `15 passed`.
- `python -m compileall -q src` : succès.
- `git diff --check` : succès.

## Risques résiduels et suite

- Les anciennes stratégies produisent encore `TradingSignal` et fixent parfois
  leur volume avant l'allocation : elles ne sont pas une preuve de parité avec
  le nouveau contrat.
- Les métadonnées publiques Kraken doivent être collectées et versionnées avant
  qu'une simulation puisse se dire exécutable par paire.
- Les fills partiels, stops et récupérations du moteur paper historique restent
  à consolider dans le Bloc 5. Ils bloquent toute revue de paper capital.
- Le Bloc 4 unifiera le shadow autour des mêmes données, features, artefacts et
  décisions, sans relier ce nouveau simulateur à un ordre réel.
