# 🛠️ Template - Implémentation Data Connector

## Structure des dossiers

```
src/
├── data_connector/
│   ├── __init__.py
│   ├── core/
│   │   ├── __init__.py
│   │   ├── event_bus.py          # Bus d'événements (Redis/RabbitMQ)
│   │   ├── cache_manager.py      # Gestion multi-niveaux cache
│   │   ├── rate_limiter.py       # Token bucket rate limiting
│   │   └── circuit_breaker.py    # Circuit breaker pattern
│   ├── connectors/
│   │   ├── __init__.py
│   │   ├── base.py               # Classe abstraite Connector
│   │   ├── interactive_brokers.py # Connecteur IB TWS
│   │   ├── bloomberg.py          # Connecteur BPIPE (futur)
│   │   └── alphavantage.py       # Connecteur AlphaVantage (existant)
│   ├── validators/
│   │   ├── __init__.py
│   │   ├── schema.py             # Schémas Pydantic
│   │   └── quality.py            # Validation qualité données
│   ├── models/
│   │   ├── __init__.py
│   │   ├── tick.py               # Modèle Tick
│   │   ├── ohlcv.py              # Modèle OHLCV
│   │   └── orderbook.py          # Modèle OrderBook
│   └── utils/
│       ├── __init__.py
│       ├── logger.py             # Logging structuré
│       └── metrics.py            # Métriques Prometheus
```

## Classe Base (À implémenter)

```python
# src/data_connector/connectors/base.py
from abc import ABC, abstractmethod
from typing import AsyncIterator, Optional
from pydantic import BaseModel
import asyncio

class DataConnector(ABC):
    """
    Classe abstraite pour tous les connecteurs de données.
    Tout nouveau connecteur doit hériter de cette classe.
    """
    
    def __init__(self, config: dict):
        self.config = config
        self.is_connected = False
        self._circuit_breaker = None
        self._rate_limiter = None
        
    @abstractmethod
    async def connect(self) -> bool:
        """Établit la connexion au provider. Returns: success"""
        pass
    
    @abstractmethod
    async def disconnect(self) -> None:
        """Ferme proprement la connexion"""
        pass
    
    @abstractmethod
    async def subscribe_ticks(self, symbol: str) -> AsyncIterator[Tick]:
        """Stream de ticks temps réel"""
        pass
    
    @abstractmethod
    async def subscribe_ohlcv(self, symbol: str, timeframe: str) -> AsyncIterator[OHLCV]:
        """Stream de bougies OHLCV"""
        pass
    
    @abstractmethod
    async def get_historical(self, symbol: str, start: datetime, end: datetime) -> list:
        """Récupération données historiques"""
        pass
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Nom unique du connecteur"""
        pass
    
    @property
    @abstractmethod
    def health(self) -> dict:
        """Status santé du connecteur"""
        pass
```

## Connecteur Interactive Brokers (Spécifications)

```python
# src/data_connector/connectors/interactive_brokers.py

class InteractiveBrokersConnector(DataConnector):
    """
    Connecteur Interactive Brokers via TWS API
    """
    
    NAME = "interactive_brokers"
    HOST = "127.0.0.1"
    PORT = 7497  # Paper trading
    CLIENT_ID = 1
    
    # Rate limits IB
    MAX_REQUESTS_PER_SECOND = 50
    MAX_TICK_STREAMS = 100  # Limite IB
    
    async def connect(self) -> bool:
        # Implémentation avec ib_insync
        # Gestion reconnexion automatique
        # Heartbeat toutes les 30s
        pass
    
    async def subscribe_ticks(self, symbol: str) -> AsyncIterator[Tick]:
        # Abonnement temps réel
        # Validation schéma
        # Publication sur event bus
        pass
    
    def _handle_error(self, error_code: int, error_msg: str):
        # Mapping codes erreur IB
        # 502: Connection lost → Reconnexion
        # 504: Not connected → Retry
        # 2104: Warning market data farm → Log only
        pass
```

## Configuration (config.yaml)

```yaml
data_connector:
  # Cache configuration
  cache:
    l1_ttl: 5           # 5 secondes pour ticks
    l2_ttl: 300         # 5 minutes pour OHLCV
    redis_url: "redis://localhost:6379"
  
  # Rate limiting
  rate_limiter:
    requests_per_second: 50
    burst_size: 100
  
  # Circuit breaker
  circuit_breaker:
    failure_threshold: 10
    recovery_timeout: 60
    half_open_max_calls: 3
  
  # Connecteurs
  connectors:
    interactive_brokers:
      enabled: true
      host: "127.0.0.1"
      port: 7497
      client_id: 1
      paper_trading: true
    
    bloomberg:
      enabled: false  # Future implementation
```

## Tests Requis

### Tests unitaires (coverage > 90%)
```python
# tests/test_ib_connector.py
import pytest
from unittest.mock import Mock, patch

class TestIBConnector:
    
    @pytest.mark.asyncio
    async def test_connect_success(self):
        # Test connexion réussie
        pass
    
    @pytest.mark.asyncio  
    async def test_reconnect_on_disconnect(self):
        # Test reconnexion auto
        pass
    
    @pytest.mark.asyncio
    async def test_rate_limiting(self):
        # Test respect rate limits
        pass
    
    @pytest.mark.asyncio
    async def test_circuit_breaker(self):
        # Test ouverture circuit breaker après N échecs
        pass
```

### Tests d'intégration
- Connexion IB paper trading
- Stream ticks 1 heure sans perte
- Reconnexion après coupure réseau simulée

### Tests de charge
- 1000 ticks/seconde
- 50 symboles simultanés
- Latence p95 < 100ms

## Checklist de Validation

### Avant merge (Review Claude)
- [ ] Code suit PEP8
- [ ] Type hints complets
- [ ] Docstrings présentes
- [ ] Tests unitaires > 90%
- [ ] Pas de secrets dans le code
- [ ] Gestion erreurs complète
- [ ] Logs structurés
- [ ] Métriques exposées

### Validation fonctionnelle (Kimi)
- [ ] Connexion stable 24h
- [ ] Reconnexion automatique fonctionne
- [ ] Rate limiting respecté
- [ ] Cache hit rate > 80%
- [ ] Circuit breaker opérationnel
- [ ] Documentation complète

## Notes pour Devin

1. **Commencer par** : Connecteur IB avec reconnexion auto
2. **Utiliser** : ib_insync (plus simple que API officielle)
3. **Tester avec** : Paper trading IB (port 7497)
4. **Ne pas oublier** : Gestion des erreurs IB spécifiques
5. **Priorité** : Robustesse > Performance > Features

## Références

- [ib_insync doc](https://ib-insync.readthedocs.io/)
- [IB API Error Codes](https://interactivebrokers.github.io/tws-api/message_codes.html)
- ADR-001, ADR-002, ADR-003