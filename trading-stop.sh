#!/bin/bash
# trading-stop.sh - Arrêter l'équipe proprement

echo "🛑 Arrêt de l'équipe trading..."
docker-compose -f docker-compose.trading.yml down --remove-orphans
echo "✅ Équipe arrêtée"
