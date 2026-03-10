#!/bin/bash
# trading-status.sh - Vérifier l'état de l'équipe

echo "╔════════════════════════════════════════╗"
echo "║   📊 STATUT ÉQUIPE TRADING             ║"
echo "╚════════════════════════════════════════╝"
echo ""

# Statut des conteneurs
echo "🐳 Conteneurs:"
docker-compose -f docker-compose.trading.yml ps

echo ""
echo "🔗 Event Bus (port 18789):"
if docker exec trading-event-bus redis-cli ping 2>/dev/null | grep -q "PONG"; then
    echo "  ✅ Connecté"
    echo "  📡 Canaux actifs:"
    docker exec trading-event-bus redis-cli PUBSUB CHANNELS 2>/dev/null | head -10
else
    echo "  ❌ Déconnecté"
fi

echo ""
echo "💓 Heartbeat (5min):"
docker logs heartbeat-monitor --tail 5 2>/dev/null | tail -3

echo ""
echo "💰 Budgets:"
echo "  Kimi Dev:      20€ (économique)"
echo "  Gemini Review: 20€ (économique)"
echo "  Opus Security: 20$ (critique - préservé)"
