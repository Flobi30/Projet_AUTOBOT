# AUTOBOT - Guide d'assemblage du Bot Grid Trading

## Architecture

```
scripts/
  kraken_connect.py    -> Connexion API Kraken (ccxt)
  get_price.py         -> Prix BTC/EUR temps reel (API publique)
  grid_calculator.py   -> Calcul 15 niveaux grid
  order_manager.py     -> Placement ordres achat LIMIT
  position_manager.py  -> Detection fills + placement ventes
  persistence.py       -> Sauvegarde etat JSON
  main.py              -> Orchestrateur principal
  test_assembly.py     -> Test d'assemblage

src/autobot/
  error_handler.py     -> Gestion erreurs, retry, circuit breaker
```

## Pre-requis

```bash
pip install ccxt requests
```

Variables d'environnement requises :

```bash
export KRAKEN_API_KEY=votre_cle_api
export KRAKEN_API_SECRET=votre_cle_privee
```

## Lancement

### 1. Test d'assemblage (sans Kraken)

```bash
cd scripts
python test_assembly.py
```

### 2. Dry-run (verification imports + config)

```bash
cd scripts
python main.py --dry-run
```

### 3. Lancement du bot

```bash
cd scripts
python main.py
```

Arret propre : `Ctrl+C`

## Configuration

Dans `scripts/main.py` :

| Parametre      | Valeur | Description                    |
|----------------|--------|--------------------------------|
| GRID_CAPITAL   | 500.0  | Capital total en EUR           |
| GRID_LEVELS    | 15     | Nombre de niveaux              |
| GRID_RANGE     | 14.0   | Range total +/- 7%            |
| POLL_INTERVAL  | 10     | Intervalle de polling (sec)    |

## Flux du bot

1. Connexion Kraken (authentifiee)
2. Recuperation prix BTC/EUR
3. Calcul grid 15 niveaux autour du prix
4. Placement ordres BUY (levels 0-6)
5. Boucle : monitoring fills -> placement SELL automatique
6. Sauvegarde etat dans `bot_state.json`

## Persistance

L'etat du bot est sauvegarde dans `bot_state.json` :
- Ordres places (IDs Kraken, prix, volumes)
- Positions (cycles BUY->SELL)
- Flag d'initialisation

Le bot reprend automatiquement au redemarrage si le grid est deja initialise.
