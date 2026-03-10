# 📘 ADR - UI React Dashboard

## ADR-005: Architecture Frontend Trading

### Contexte
Dashboard temps réel pour monitoring et contrôle:
- Flux données WebSocket (<100ms latence)
- Graphiques interactifs
- Gestion positions manuelle
- Alertes visuelles

### Décision
**React 18 + TypeScript + WebSocket + TradingView Charts**

```
┌─────────────────────────────────────────────────────────────┐
│                     REACT DASHBOARD                         │
├─────────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │   Header     │  │   Header     │  │   Header     │     │
│  │   P&L Total  │  │   Connexion  │  │   Alertes    │     │
│  └──────────────┘  └──────────────┘  └──────────────┘     │
├─────────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────────────────────────┐    │
│  │  Watchlist   │  │         Main Chart               │    │
│  │  (Tickers)   │  │     (TradingView Widget)         │    │
│  │              │  │                                  │    │
│  │  • BTC/USD   │  │  • Candlestick temps réel        │    │
│  │  • EUR/USD   │  │  • Indicateurs techniques        │    │
│  │  • AAPL      │  │  • Order book visuel             │    │
│  └──────────────┘  └──────────────────────────────────┘    │
├─────────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │   Positions  │  │   Order      │  │   Risk       │     │
│  │   Ouvertes   │  │   Entry      │  │   Metrics    │     │
│  │              │  │              │  │              │     │
│  │  Symbol      │  │  [Buy]       │  │  VaR: 1.5%   │     │
│  │  Size        │  │  [Sell]      │  │  DD: 3.2%    │     │
│  │  P&L         │  │  Size: ___   │  │  Exposure    │     │
│  │  Close [X]   │  │  SL/TP       │  │  Leverage    │     │
│  └──────────────┘  └──────────────┘  └──────────────┘     │
├─────────────────────────────────────────────────────────────┤
│  ┌──────────────────────────────────────────────────────┐  │
│  │              Log / Journal Transactions              │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

### Stack Technique

```json
{
  "dependencies": {
    "react": "^18.2.0",
    "typescript": "^5.0.0",
    "react-query": "^3.39.0",      // Cache serveur
    "zustand": "^4.3.0",           // State management
    "recharts": "^2.5.0",          // Charts basiques
    "tradingview-chart": "latest", // TradingView widget
    "ws": "^8.13.0",               // WebSocket client
    "tailwindcss": "^3.3.0",       // Styling
    "react-hot-toast": "^2.4.0"    // Notifications
  }
}
```

### Architecture State Management

```typescript
// store/tradingStore.ts
interface TradingState {
  // Data
  tickers: Ticker[];
  positions: Position[];
  orders: Order[];
  
  // Connection
  wsStatus: 'connected' | 'disconnected' | 'reconnecting';
  lastUpdate: Date;
  
  // Risk
  dailyPnL: number;
  totalPnL: number;
  currentDrawdown: number;
  var95: number;
  
  // Actions
  connectWebSocket: () => void;
  disconnectWebSocket: () => void;
  placeOrder: (order: Order) => void;
  closePosition: (id: string) => void;
}
```

### WebSocket Hook

```typescript
// hooks/useWebSocket.ts
export const useWebSocket = () => {
  const [status, setStatus] = useState<'connected' | 'disconnected'>('disconnected');
  
  useEffect(() => {
    const ws = new WebSocket('ws://localhost:18789/data-stream');
    
    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      updateStore(data);
    };
    
    ws.onclose = () => {
      setStatus('disconnected');
      // Auto reconnect
      setTimeout(connectWebSocket, 5000);
    };
    
    return () => ws.close();
  }, []);
  
  return { status };
};
```

### Performance Targets

| Métrique | Objectif |
|----------|----------|
| First Contentful Paint | < 1.5s |
| Time to Interactive | < 3s |
| WebSocket latency | < 100ms |
| Chart update rate | 60 FPS |
| Memory usage | < 200MB |

### Responsive Design

```css
/* Breakpoints */
- Mobile: < 768px (simplifié, 1 colonne)
- Tablet: 768px - 1024px (2 colonnes)
- Desktop: > 1024px (layout complet)
- Ultra-wide: > 2560px (multi-charts)
```

### Sécurité Frontend

1. **Pas de clés API en dur** → Variables d'environnement
2. **Validation inputs** → Zod schemas
3. **XSS protection** → React sanitize
4. **CSP headers** → Config nginx

---

**Date:** 2026-02-04  
**Décideur:** Kimi  
**Status:** APPROVED - Prêt pour développement