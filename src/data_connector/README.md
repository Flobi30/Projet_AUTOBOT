# Data Connector Module

Module de connectivité robuste pour Interactive Brokers dans le système AUTOBOT.

## Architecture

```
src/data_connector/
├── __init__.py          # Exports publics
├── base.py              # Classes de base et interfaces
├── exceptions.py        # Exceptions personnalisées
├── ib_connector.py      # Connecteur Interactive Brokers
├── rate_limiter.py      # Rate limiting (Token Bucket)
├── circuit_breaker.py   # Circuit Breaker pattern
├── heartbeat.py         # Monitoring de connexion
└── README.md            # Documentation
```

## Fonctionnalités

### Connecteur Interactive Brokers

Le connecteur IB (`IBConnector`) fournit une interface robuste pour TWS/Gateway avec:

- Support paper trading (port 7497) et live trading (port 7496)
- Reconnexion automatique avec backoff exponentiel
- Gestion des erreurs IB (502, 504, 1100)
- Rate limiting à 50 req/sec
- Circuit breaker pour tolérance aux pannes
- Heartbeat monitoring
- Logs structurés JSON
- Tracking de latence (cible p95 < 100ms)

### Patterns de Résilience

#### Rate Limiter (Token Bucket)

```python
from src.data_connector import RateLimiter

limiter = RateLimiter(rate=50.0, burst=50)

# Utilisation async
await limiter.acquire()

# Utilisation non-bloquante
if limiter.try_acquire():
    # Procéder avec la requête
    pass
```

#### Circuit Breaker

```python
from src.data_connector import CircuitBreaker

breaker = CircuitBreaker(
    failure_threshold=5,
    timeout=60.0,
    name="ib_connector"
)

# Utilisation manuelle
if breaker.allow_request():
    try:
        result = await operation()
        breaker.record_success()
    except Exception:
        breaker.record_failure()
        raise

# Utilisation avec décorateur
@breaker.protect
async def protected_operation():
    return await some_operation()
```

#### Heartbeat Monitor

```python
from src.data_connector import HeartbeatMonitor

async def health_check():
    return await connector.health_check()

monitor = HeartbeatMonitor(
    health_check=health_check,
    on_connection_lost=handle_disconnect,
    interval=10.0,
    timeout=30.0
)

await monitor.start()
```

## Utilisation

### Configuration

```python
from src.data_connector import IBConnector, IBConnectorConfig

# Configuration manuelle
config = IBConnectorConfig(
    host="127.0.0.1",
    port=7497,  # Paper trading
    client_id=1,
    timeout=30.0,
    max_reconnect_attempts=5,
    rate_limit=50
)

# Configuration depuis variables d'environnement
config = IBConnectorConfig.from_env()
```

Variables d'environnement supportées:
- `IB_HOST`: Adresse du serveur TWS/Gateway
- `IB_PORT`: Port (7497 paper, 7496 live)
- `IB_CLIENT_ID`: ID client unique
- `IB_READONLY`: Mode lecture seule
- `IB_ACCOUNT`: Compte spécifique
- `IB_TIMEOUT`: Timeout de connexion
- `IB_MAX_RECONNECT`: Tentatives de reconnexion max
- `IB_RECONNECT_DELAY`: Délai entre reconnexions
- `IB_HEARTBEAT_INTERVAL`: Intervalle heartbeat
- `IB_RATE_LIMIT`: Limite de requêtes/sec

### Connexion

```python
connector = IBConnector(config)

# Connexion manuelle
await connector.connect()
# ... opérations ...
await connector.disconnect()

# Avec context manager
async with connector:
    ticker = await connector.get_ticker("AAPL")
```

### Données de Marché

```python
# Ticker en temps réel
ticker = await connector.get_ticker("AAPL")
print(f"Bid: {ticker['bid']}, Ask: {ticker['ask']}")

# Données historiques
bars = await connector.get_historical_data(
    symbol="AAPL",
    duration="1 D",
    bar_size="1 min",
    what_to_show="TRADES"
)
```

### Compte et Positions

```python
# Résumé du compte
summary = await connector.get_account_summary()
print(f"Net Liquidation: {summary['NetLiquidation']}")

# Positions ouvertes
positions = await connector.get_positions()
for pos in positions:
    print(f"{pos['symbol']}: {pos['position']} @ {pos['avg_cost']}")
```

### Ordres

```python
# Placer un ordre market
order = await connector.place_order(
    symbol="AAPL",
    action="BUY",
    quantity=100,
    order_type="MKT"
)

# Placer un ordre limit
order = await connector.place_order(
    symbol="AAPL",
    action="SELL",
    quantity=100,
    order_type="LMT",
    limit_price=150.00
)

# Annuler un ordre
await connector.cancel_order(order["order_id"])

# Lister les ordres ouverts
orders = await connector.get_open_orders()
```

### Monitoring

```python
# Statut complet
status = connector.get_status()
print(f"State: {status['state']}")
print(f"P95 Latency: {status['metrics']['p95_latency_ms']}ms")
print(f"Circuit Breaker: {status['circuit_breaker']['state']}")
```

## Gestion des Erreurs IB

Le connecteur gère automatiquement les erreurs IB suivantes:

| Code | Description | Action |
|------|-------------|--------|
| 502 | Couldn't connect to TWS | Reconnexion automatique |
| 504 | Not connected | Reconnexion automatique |
| 1100 | Connectivity lost | Reconnexion automatique |
| 1101 | Connectivity restored (data lost) | Log info |
| 1102 | Connectivity restored (data maintained) | Log info |
| 2103 | Market data farm broken | Reconnexion automatique |
| 2104 | Market data farm OK | Log info |

## Tests

```bash
# Exécuter tous les tests
pytest tests/data_connector/ -v

# Avec couverture
pytest tests/data_connector/ -v --cov=src/data_connector --cov-report=html
```

## Contraintes

- Paper trading IB: port 7497
- Rate limit: 50 req/sec
- Latence cible: p95 < 100ms
- Pas de secrets en dur
- Logs structurés JSON

## Dépendances

- `ib_insync`: Client IB async (optionnel, mock disponible)
- `asyncio`: Support async/await
- Python 3.11+
