# Data Connector Module

Architecture modulaire event-driven pour la collecte de données de marché multi-sources.

## Vue d'ensemble

Le module Data Connector fournit une infrastructure robuste pour:
- Connexion à Interactive Brokers (TWS API)
- Collecte simultanée depuis plusieurs APIs tierces (TwelveData, AlphaVantage, Binance, Coinbase, Kraken)
- Rate limiting adaptatif avec token bucket algorithm
- Cache LRU avec TTL et persistance disque
- Validation des données avec détection d'anomalies

## Architecture

```
data_connector/
├── base.py              # Classes de base event-driven
├── rate_limiter.py      # Rate limiting multi-provider
├── cache.py             # Cache LRU avec persistance
├── validator.py         # Validation et détection d'anomalies
├── ib_connector.py      # Connecteur Interactive Brokers
└── third_party_connector.py  # Connecteur APIs tierces
```

## Utilisation

### Connecteur Interactive Brokers

```python
from data_connector import IBConnector, IBConfig

config = IBConfig(
    host="127.0.0.1",
    port=7497,  # Paper trading
    client_id=1,
)

connector = IBConnector(config=config)
await connector.connect()
await connector.subscribe("AAPL")

data = await connector.get_market_data("AAPL")
print(f"Prix: {data.last}")

historical = await connector.get_historical_data("AAPL", start, end, "1h")
```

### Connecteur APIs Tierces (Collecte Simultanée)

```python
from data_connector import ThirdPartyConnector, ThirdPartyConfig

config = ThirdPartyConfig(
    providers=["binance", "coinbase", "kraken", "twelvedata"],
    simultaneous_collection=True,  # Collecte depuis toutes les APIs en parallèle
    twelvedata_api_key="your_key",
)

connector = ThirdPartyConnector(config=config)
await connector.connect()

# Données agrégées de toutes les sources
data = await connector.get_market_data("BTC/USD")
```

### Rate Limiting

```python
from data_connector import RateLimiter, RateLimitConfig, MultiProviderRateLimiter

# Limiter simple
config = RateLimitConfig(
    requests_per_second=10.0,
    requests_per_minute=500,
    burst_size=20,
    adaptive=True,  # Backoff automatique sur 429
)
limiter = RateLimiter(config=config, name="my_api")

acquired, wait_time = limiter.acquire()
if not acquired:
    await asyncio.sleep(wait_time)

# Multi-provider avec configs prédéfinies
multi = MultiProviderRateLimiter()
await multi.wait_and_acquire("binance")
```

### Cache

```python
from data_connector import DataCache, CacheConfig, MarketDataCache

config = CacheConfig(
    max_size=10000,
    default_ttl=300.0,
    persist_to_disk=True,
    persist_path="/data/cache",
)

cache = MarketDataCache(config=config)
cache.set_symbol_data("AAPL", market_data, source="binance")
data = cache.get_symbol_data("AAPL", source="binance")
```

### Validation

```python
from data_connector import DataValidator, ValidationRule, AnomalyDetector

validator = DataValidator()

# Ajouter règle personnalisée
validator.add_rule(ValidationRule(
    name="max_price",
    field="last",
    validator=lambda v, _: v is None or v < 1000000,
    message="Prix trop élevé",
))

result = validator.validate(market_data)
if not result.is_valid:
    for issue in result.errors:
        print(f"Erreur: {issue.message}")

# Détection d'anomalies
detector = AnomalyDetector(z_score_threshold=3.0)
issues = detector.check(market_data)
```

## Events

Le système utilise une architecture event-driven:

```python
from data_connector import EventType

connector.events.on(EventType.CONNECTED, lambda e: print("Connecté!"))
connector.events.on(EventType.DATA_RECEIVED, lambda e: process_data(e.data))
connector.events.on(EventType.ERROR, lambda e: log_error(e.error))
```

Types d'événements disponibles:
- `CONNECTED`, `DISCONNECTED`, `RECONNECTING`
- `DATA_RECEIVED`, `DATA_ERROR`
- `SUBSCRIPTION_ADDED`, `SUBSCRIPTION_REMOVED`
- `RATE_LIMITED`, `CACHE_HIT`, `CACHE_MISS`
- `VALIDATION_ERROR`, `ANOMALY_DETECTED`

## Patterns pour Nouveaux Connecteurs

Pour créer un nouveau connecteur:

1. Hériter de `BaseConnector`
2. Implémenter les méthodes abstraites:
   - `connect()`, `disconnect()`
   - `subscribe()`, `unsubscribe()`
   - `get_market_data()`, `get_historical_data()`
3. Utiliser `self.events.emit()` pour les événements
4. Intégrer rate limiter et cache si nécessaire

```python
from data_connector.base import BaseConnector, MarketData, EventType

class MyConnector(BaseConnector):
    def __init__(self, config=None):
        super().__init__(name="my_connector")
        self.config = config or MyConfig()
        self._rate_limiter = RateLimiter(name="my_api")
        self._cache = MarketDataCache()
    
    async def connect(self) -> bool:
        # Logique de connexion
        self._set_status(ConnectionStatus.CONNECTED)
        return True
    
    async def get_market_data(self, symbol: str) -> Optional[MarketData]:
        # Vérifier cache
        cached = self._cache.get_symbol_data(symbol)
        if cached:
            self.events.emit(EventType.CACHE_HIT, data=cached)
            return cached
        
        # Rate limiting
        acquired, wait = await self._rate_limiter.acquire_async()
        if not acquired:
            await asyncio.sleep(wait)
        
        # Récupérer données
        data = await self._fetch_data(symbol)
        
        # Valider et cacher
        self._cache.set_symbol_data(symbol, data)
        return data
```

## Configuration Environnement

Variables d'environnement supportées:
- `TWELVEDATA_API_KEY`
- `ALPHAVANTAGE_API_KEY`
- `BINANCE_API_KEY`, `BINANCE_API_SECRET`
- `COINBASE_API_KEY`, `COINBASE_API_SECRET`
- `KRAKEN_API_KEY`, `KRAKEN_API_SECRET`

## Tests

```bash
pytest tests/test_data_connector/ -v
```

Coverage: >90% sur tous les composants.
