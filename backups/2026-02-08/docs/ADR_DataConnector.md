# 📘 Architecture Decision Record - AUTOBOT Data Connector

## ADR-001: Architecture Event-Driven pour Data Connector

### Contexte
AUTOBOT nécessite un système de collecte de données capable de gérer:
- Multi-providers (IB, Bloomberg, données temps réel)
- Haute disponibilité 24/7
- Résilience aux pannes
- Scalabilité horizontale

### Décision
Architecture **Event-Driven** avec pattern **CQRS** (Command Query Responsibility Segregation)

```
┌─────────────────┐     ┌──────────────┐     ┌─────────────────┐
│   Data Sources  │────▶│ Event Bus    │────▶│   Processors    │
│  (IB, Bloomberg)│     │ (Redis/Rabbit)│     │ (Validation,    │
└─────────────────┘     └──────────────┘     │  Normalization) │
                                              └────────┬────────┘
                                                       │
                              ┌────────────────────────┼────────────────────────┐
                              │                        │                        │
                              ▼                        ▼                        ▼
                       ┌────────────┐          ┌────────────┐          ┌────────────┐
                       │   Cache    │          │   Store    │          │  Strategy  │
                       │  (Hot)     │          │  (Cold)    │          │   Engine   │
                       └────────────┘          └────────────┘          └────────────┘
```

### Conséquences

✅ **Avantages:**
- Découplage total des composants
- Résilience naturelle (replay d'événements)
- Scalabilité horizontale facile
- Testabilité accrue

❌ **Inconvénients:**
- Complexité accrue
- Latence introduite par le bus
- Debugging plus difficile
- Nécessite monitoring robuste

### Alternatives rejetées
- **Architecture monolithique**: Trop rigide
- **Microservices purs**: Trop complexe pour MVP
- **Polling synchrone**: Pas scalable

---

## ADR-002: Connecteur Interactive Brokers (TWS API)

### Contexte
Besoin de connecteur institutionnel supportant:
- Forex + Crypto + Stocks
- Exécution algorithmique
- Faible latence
- Coûts maîtrisés

### Décision
**ib_insync** (Python async) + **WebSocket** pour streaming temps réel

### Spécifications techniques

```python
class IBConnector:
    """
    Connecteur Interactive Brokers pour AUTOBOT
    """
    
    # Configuration
    HOST = '127.0.0.1'
    PORT = 7497  # TWS paper trading
    CLIENT_ID = 1
    
    # Rate Limiting
    MAX_REQUESTS_PER_SECOND = 50
    MAX_CONCURRENT_CONNECTIONS = 1
    
    # Retry Policy
    MAX_RETRIES = 5
    BACKOFF_BASE = 2  # secondes
    
    # Circuit Breaker
    FAILURE_THRESHOLD = 10
    RECOVERY_TIMEOUT = 60  # secondes
```

### Gestion des erreurs

| Code erreur | Action | Retry |
|-------------|--------|-------|
| 502 (Connection lost) | Reconnexion auto | Oui |
| 504 (Not connected) | Attente + retry | Oui |
| 2104 (Market data farm) | Warning log | Non |
| 2106 (HMDS data farm) | Warning log | Non |
| 1100 (Connectivity) | Circuit breaker | Oui |

---

## ADR-003: Stratégie de Cache Multi-Niveau

### Contexte
Optimiser les performances tout en minimisant les coûts API

### Décision
**Cache L1 (Local)** + **Cache L2 (Redis)** + **Cache L3 (Parquet files)**

```
Requête Data
     │
     ▼
┌────────────┐
│   L1 RAM   │ ◀── TTL: 5s (tick), 60s (OHLCV)
│  (Python)  │
└─────┬──────┘
      │ Miss
      ▼
┌────────────┐
│   L2 Redis │ ◀── TTL: 5min (hot), 1h (warm)
│   (Remote) │
└─────┬──────┘
      │ Miss
      ▼
┌────────────┐
│ L3 Parquet │ ◀── Historical data
│   (Disk)   │
└─────┬──────┘
      │ Miss
      ▼
   API Provider
```

### Invalidation
- **Time-based**: TTL configurables par type de données
- **Event-based**: Publication sur update du provider
- **Manual**: Flush complet via commande admin

---

## Patterns à réutiliser

### 1. Circuit Breaker
```python
from pybreaker import CircuitBreaker

breaker = CircuitBreaker(fail_max=10, reset_timeout=60)

@breaker
def fetch_data():
    # Appel API
    pass
```

### 2. Rate Limiter (Token Bucket)
```python
from ratelimit import limits, sleep_and_retry

@sleep_and_retry
@limits(calls=50, period=1)
def api_call():
    pass
```

### 3. Retry avec Backoff
```python
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=2, min=4, max=60)
)
def connect():
    pass
```

---

## Sécurité

### Clés API
- Stockage: Variables d'environnement UNIQUEMENT
- Rotation: Automatique tous les 90 jours
- Audit: Logs de toutes les accès

### Validation des données
```python
from pydantic import BaseModel, validator

class TickData(BaseModel):
    symbol: str
    price: float
    timestamp: datetime
    
    @validator('price')
    def price_must_be_positive(cls, v):
        if v <= 0:
            raise ValueError('Price must be positive')
        return v
```

---

## Métriques à surveiller

| Métrique | Seuil alerte | Action |
|----------|--------------|--------|
| Latence p95 | > 100ms | Scale up |
| Error rate | > 1% | Circuit breaker |
| Cache hit rate | < 80% | Optimisation |
| Memory usage | > 80% | Alerting |

---

## Dépendances

```txt
ib_insync>=0.9.70
redis>=4.5.0
pydantic>=2.0.0
pybreaker>=1.0.0
ratelimit>=2.2.1
tenacity>=8.2.0
```

---

**Date:** 2026-02-04  
**Décideur:** Kimi (Architecte AUTOBOT)  
**Status:** APPROVED