#!/bin/bash
# trading-team.sh - Script de démarrage équipe trading

set -e

# Couleurs pour les logs
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}╔════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║   🚀 DÉMARRAGE ÉQUIPE TRADING          ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════╝${NC}"
echo ""

# Vérifier les clés API
echo -e "${YELLOW}🔑 Vérification des clés API...${NC}"

if [ -z "$ANTHROPIC_API_KEY" ]; then
    echo -e "${RED}❌ ANTHROPIC_API_KEY manquante${NC}"
    echo "   → Opus Security ne pourra pas démarrer"
    exit 1
fi
echo -e "${GREEN}✅ ANTHROPIC_API_KEY présente${NC}"

if [ -z "$GOOGLE_API_KEY" ]; then
    echo -e "${YELLOW}⚠️  GOOGLE_API_KEY manquante${NC}"
    echo "   → Gemini Reviewer utilisera le mode fallback"
else
    echo -e "${GREEN}✅ GOOGLE_API_KEY présente${NC}"
fi

echo ""

# Vérifier les fichiers de configuration
echo -e "${YELLOW}📁 Vérification des fichiers...${NC}"

if [ ! -f "trading-team.json" ]; then
    echo -e "${RED}❌ trading-team.json introuvable${NC}"
    exit 1
fi
echo -e "${GREEN}✅ Configuration équipe chargée${NC}"

if [ ! -f "docker-compose.trading.yml" ]; then
    echo -e "${RED}❌ docker-compose.trading.yml introuvable${NC}"
    exit 1
fi
echo -e "${GREEN}✅ Docker Compose chargé${NC}"

echo ""

# Arrêter les anciens conteneurs s'ils existent
echo -e "${YELLOW}🛑 Arrêt des anciens conteneurs...${NC}"
docker-compose -f docker-compose.trading.yml down --remove-orphans 2>/dev/null || true
echo -e "${GREEN}✅ Prêt${NC}"

echo ""

# Démarrer l'équipe
echo -e "${YELLOW}▶️  Démarrage des agents...${NC}"
docker-compose -f docker-compose.trading.yml up -d --build

echo ""
echo -e "${GREEN}╔════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║   ✅ ÉQUIPE DÉMARRÉE AVEC SUCCÈS       ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════╝${NC}"
echo ""

# Attendre que tout soit prêt
echo -e "${YELLOW}⏳ Attente de l'initialisation (10s)...${NC}"
sleep 10

# Vérifier l'état
echo ""
echo -e "${YELLOW}📊 État des agents:${NC}"
docker-compose -f docker-compose.trading.yml ps

echo ""
echo -e "${YELLOW}🔗 Vérification des connexions...${NC}"

# Test Event Bus
if docker exec trading-event-bus redis-cli ping | grep -q "PONG"; then
    echo -e "${GREEN}✅ Event Bus (port 18789) - CONNECTÉ${NC}"
else
    echo -e "${RED}❌ Event Bus - DÉCONNECTÉ${NC}"
fi

echo ""
echo -e "${GREEN}🎯 L'équipe est prête à trader !${NC}"
echo ""
echo "Commandes utiles:"
echo "  ./trading-status.sh    → Voir le statut des agents"
echo "  ./trading-logs.sh      → Voir les logs"
echo "  ./trading-stop.sh      → Arrêter l'équipe"
echo ""
