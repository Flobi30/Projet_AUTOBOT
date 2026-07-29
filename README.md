# Projet AUTOBOT

AUTOBOT est actuellement une plateforme de recherche quantitative et de shadow non executable. Le runtime officiel utilise les donnees publiques et ne peut ni creer d'ordre, ni allouer du capital paper, ni promouvoir une strategie, ni activer le live.

## References canoniques

- [Fondation et contrats](docs/architecture/AUTOBOT_FOUNDATION.md)
- [Matrice des 24 couches](docs/architecture/layer_coverage.json)
- [Regles de contribution](AGENTS.md)
- [Runbook research/shadow](docs/runbooks/RESEARCH_SHADOW_INCIDENTS.md)

Une couche ne devient `VERIFIED` qu'avec le code, les tests reproductibles et une preuve runtime controlee. En l'absence de ces trois preuves, AUTOBOT reste fail-closed et ne pretend pas avoir un edge ou une performance future.

## Demarrage securise

1. Copiez `.env.example` vers `.env` sans y ajouter de cle d'exchange.
2. Conservez `AUTOBOT_OBSERVATION_ONLY_RUNTIME=true` et tous les verrous d'execution a `false`.
3. Utilisez les commandes de recherche et d'audit depuis la racine du depot.

| Variable | Obligatoire | Valeur du programme |
|---|---|---|
| `AUTOBOT_OBSERVATION_ONLY_RUNTIME` | oui | `true` |
| `PAPER_TRADING` | oui | `false` |
| `PREFLIGHT_ONLY` | oui | `true` |
| `PAPER_EXECUTION_ADAPTER_ENABLED` | oui | `false` |
| `PAPER_EXECUTION_ROUTER_ENABLED` | oui | `false` |
| `PAPER_TEST_TRADING_ENABLED` | oui | `false` |
| `AUTOBOT_REAL_ORDER_EXECUTION_ENABLED` | oui | `false` |
| `COLONY_AUTO_LIVE_PROMOTION` | oui | `false` |
| `STRATEGY_ROUTER_LIVE_ENABLED` | oui | `false` |
| `LIVE_TRADING_CONFIRMATION` | oui | `false` |

Un dossier de readiness est une preuve de revue humaine; il ne peut jamais activer paper, live ou promotion :

```bash
python -m autobot.v2.cli paper-readiness-dossier --coverage-path docs/architecture/layer_coverage.json --output data/research/reports/paper_readiness.md
```

Le deploiement de l'image utilise uniquement `bash deploy/rebuild-autobot-image.sh`, puis `bash deploy/verify-autobot-runtime-evidence.sh`. Ces outils refusent une preuve non alignee ou unsafe; ils ne modifient ni la politique de trading ni les flags d'execution.

Le programme ne passe pas au capital paper tant qu'une strategie n'a pas survecu aux gates de donnees, validation statistique, couts, capacite, simulation, shadow, reconciliation et resilience. Le live est hors scope.

Les anciens guides paper/live sont archives et non operationnels. Ils restent consultables dans l'historique Git uniquement pour l'audit.
