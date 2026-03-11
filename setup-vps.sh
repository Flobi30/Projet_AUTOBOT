#!/bin/bash
# Script de setup pour machine dédiée / VPS
# Usage: ./setup-vps.sh

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "================================"
echo "🚀 Setup AUTOBOT V2 sur VPS"
echo "================================"
echo ""

# Vérifie si on est root
if [ "$EUID" -ne 0 ]; then 
    echo -e "${RED}❌ Ce script doit être exécuté en root (ou avec sudo)${NC}"
    exit 1
fi

# 1. Installation Docker
echo -e "${YELLOW}📦 Installation de Docker...${NC}"
if ! command -v docker &> /dev/null; then
    curl -fsSL https://get.docker.com -o get-docker.sh
    sh get-docker.sh
    rm get-docker.sh
    systemctl enable docker
    systemctl start docker
    echo -e "${GREEN}✅ Docker installé${NC}"
else
    echo -e "${GREEN}✅ Docker déjà installé${NC}"
fi

# 2. Installation Docker Compose
if ! command -v docker-compose &> /dev/null; then
    apt update
    apt install -y docker-compose
    echo -e "${GREEN}✅ Docker Compose installé${NC}"
else
    echo -e "${GREEN}✅ Docker Compose déjà installé${NC}"
fi

# 3. Création du répertoire
INSTALL_DIR="/opt/autobot"
echo -e "${YELLOW}📁 Création du répertoire $INSTALL_DIR...${NC}"
mkdir -p $INSTALL_DIR
cd $INSTALL_DIR

# 4. Clonage du repo (ou copie si déjà présent)
if [ ! -d "$INSTALL_DIR/.git" ]; then
    echo -e "${YELLOW}📥 Clonage du repository...${NC}"
    # Si on est dans un sous-répertoire du repo, on copie
    if [ -f "$0" ] && [ -d "$(dirname $0)/.git" ]; then
        cp -r $(dirname $0)/* $INSTALL_DIR/
        cp -r $(dirname $0)/.git $INSTALL_DIR/ 2>/dev/null || true
    else
        echo -e "${RED}❌ Veuillez d'abord cloner le repository:${NC}"
        echo "git clone https://github.com/Flobi30/Projet_AUTOBOT.git /opt/autobot"
        exit 1
    fi
fi

# 5. Configuration
echo ""
echo -e "${YELLOW}⚙️ Configuration...${NC}"

if [ ! -f "$INSTALL_DIR/.env" ]; then
    echo -e "${YELLOW}📝 Création du fichier .env${NC}"
    
    # Demande les clés API
    read -p "Clé API Kraken: " KRAKEN_API_KEY
    read -s -p "Secret API Kraken: " KRAKEN_API_SECRET
    echo ""
    
    # Génère un token aléatoire pour le dashboard
    DASHBOARD_TOKEN=$(openssl rand -hex 32)
    
    cat > $INSTALL_DIR/.env << EOF
# Clés API Kraken
KRAKEN_API_KEY=$KRAKEN_API_KEY
KRAKEN_API_SECRET=$KRAKEN_API_SECRET

# Token Dashboard
DASHBOARD_API_TOKEN=$DASHBOARD_TOKEN
EOF
    
    echo -e "${GREEN}✅ Fichier .env créé${NC}"
    echo -e "${YELLOW}⚠️  Conservez ce token pour accéder au dashboard:${NC}"
    echo "$DASHBOARD_TOKEN"
else
    echo -e "${GREEN}✅ Fichier .env déjà existant${NC}"
fi

# 6. Création des répertoires de données
mkdir -p $INSTALL_DIR/data
mkdir -p $INSTALL_DIR/logs

# 7. Configuration pare-feu
echo ""
echo -e "${YELLOW}🛡️ Configuration du pare-feu...${NC}"
if command -v ufw &> /dev/null; then
    ufw default deny incoming
    ufw default allow outgoing
    ufw allow 22/tcp
    ufw --force enable
    echo -e "${GREEN}✅ Pare-feu UFW configuré${NC}"
else
    apt install -y ufw
    ufw default deny incoming
    ufw default allow outgoing
    ufw allow 22/tcp
    ufw --force enable
    echo -e "${GREEN}✅ Pare-feu UFW installé et configuré${NC}"
fi

# 8. Premier démarrage
echo ""
echo -e "${YELLOW}🚀 Premier démarrage...${NC}"
cd $INSTALL_DIR
docker-compose pull
docker-compose build
docker-compose up -d

# 9. Attente et vérification
echo ""
echo -e "${YELLOW}⏳ Vérification du démarrage...${NC}"
sleep 5

if curl -s http://localhost:8080/health > /dev/null; then
    echo -e "${GREEN}✅ AUTOBOT démarré avec succès!${NC}"
    echo ""
    echo "================================"
    echo "🎉 Installation terminée!"
    echo "================================"
    echo ""
    echo "📊 Dashboard: http://$(hostname -I | awk '{print $1}'):8080"
    echo "🔧 Gestion:"
    echo "   cd $INSTALL_DIR"
    echo "   docker-compose logs -f"
    echo "   docker-compose ps"
    echo ""
    echo "📖 Documentation: $INSTALL_DIR/DEPLOIEMENT_VPS.md"
else
    echo -e "${RED}❌ Le bot ne semble pas avoir démarré correctement${NC}"
    echo "Vérifiez les logs: docker-compose logs"
    exit 1
fi
