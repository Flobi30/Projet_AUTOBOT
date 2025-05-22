#!/bin/bash


SERVER_URL="http://localhost:8000"
COOKIE_FILE="/tmp/autobot_cookies.txt"

log() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $1"
}

log "Authentification à AUTOBOT..."
./scripts/login.sh

if [ $? -ne 0 ]; then
    log "Erreur lors de l'authentification"
    exit 1
fi

log "Configuration des seuils de performance pour un rendement cible de 10% journalier..."
curl -s -b "$COOKIE_FILE" -X POST "$SERVER_URL/api/backtest/thresholds" \
    -H "Content-Type: application/json" \
    -d '{
        "min_sharpe": 1.8,
        "max_drawdown": 12,
        "min_pnl": 10,
        "auto_live": true
    }'

log "Activation du mode Ghost et de la duplication automatique..."
curl -s -b "$COOKIE_FILE" -X POST "$SERVER_URL/api/ghosting/start" \
    -H "Content-Type: application/json" \
    -d '{
        "count": 2,
        "markets": ["BTC/USD", "ETH/USD"],
        "strategies": ["momentum", "mean_reversion"],
        "config": {
            "auto_scale": true,
            "performance_threshold": 0.08,
            "scale_factor": 1.5,
            "max_instances_per_market": 5
        }
    }'

log "Configuration terminée. AUTOBOT est maintenant configuré pour un rendement optimal avec le mode Ghost activé."
